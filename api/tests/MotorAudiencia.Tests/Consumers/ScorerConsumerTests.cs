using FluentAssertions;
using MassTransit;
using MassTransit.Testing;
using Microsoft.Extensions.DependencyInjection;
using Moq;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Domain.Events;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Domain.ValueObjects;
using MotorAudiencia.Infrastructure.Messaging.Consumers;

namespace MotorAudiencia.Tests.Consumers;

public sealed class ScorerConsumerTests : IAsyncLifetime
{
    private readonly Mock<ILeadRepository> _leads = new();
    private readonly Mock<ISourceRepository> _sources = new();
    private readonly Mock<INicheRepository> _niches = new();
    private readonly Mock<IScoreRepository> _scores = new();
    private ServiceProvider? _provider;
    private ITestHarness? _harness;

    public async Task InitializeAsync()
    {
        _provider = new ServiceCollection()
            .AddScoped<ILeadRepository>(_ => _leads.Object)
            .AddScoped<ISourceRepository>(_ => _sources.Object)
            .AddScoped<INicheRepository>(_ => _niches.Object)
            .AddScoped<IScoreRepository>(_ => _scores.Object)
            .AddMassTransitTestHarness(x => x.AddConsumer<ScorerConsumer>())
            .BuildServiceProvider(true);

        _harness = _provider.GetRequiredService<ITestHarness>();
        await _harness.Start();
    }

    public async Task DisposeAsync()
    {
        await _harness!.Stop();
        await _provider!.DisposeAsync();
    }

    private static Lead CreateEnriched(
        string name, string email, string? phone = null, string? company = null)
    {
        var lead = Lead.Create(name, email, phone, company);
        lead.AdvanceStatus(LeadStatus.Validated);
        lead.AdvanceStatus(LeadStatus.Deduplicated);
        lead.AdvanceStatus(LeadStatus.Enriched);
        return lead;
    }

    private void SetupRepos(Lead lead)
    {
        _leads.Setup(r => r.FindByIdAsync(lead.Id, It.IsAny<CancellationToken>())).ReturnsAsync(lead);
        _leads.Setup(r => r.SaveAsync(It.IsAny<Lead>(), It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);
        _sources.Setup(r => r.FindByIdAsync(It.IsAny<Guid>(), It.IsAny<CancellationToken>())).ReturnsAsync((Source?)null);
        _niches.Setup(r => r.FindByIdAsync(It.IsAny<Guid>(), It.IsAny<CancellationToken>())).ReturnsAsync((Niche?)null);
        _scores.Setup(r => r.SaveAsync(It.IsAny<Score>(), It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);
    }

    [Fact]
    public async Task FullLead_ScoresHot()
    {
        // completeness=1.0 (30) + source=0.5*25 (12.5) + phone (15) + business_domain (15) + niche=0.5*15 (7.5) = 80
        var lead = CreateEnriched("João Barbeiro", "joao@salao.com.br", phone: "11999999999", company: "Salão");
        lead.SetInstagramData("joao_salao", null, 1500, null, null, null, "business", null);
        SetupRepos(lead);

        Score? saved = null;
        _scores.Setup(r => r.SaveAsync(It.IsAny<Score>(), It.IsAny<CancellationToken>()))
               .Callback<Score, CancellationToken>((s, _) => saved = s)
               .Returns(Task.CompletedTask);

        await _harness!.Bus.Publish(new LeadEnrichedMessage(lead.Id, null, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadEnrichedMessage>()).Should().BeTrue();

        saved.Should().NotBeNull();
        saved!.Value.Should().BeGreaterThanOrEqualTo(70);
        saved.Temperature.Should().Be(Temperature.Hot);
        lead.Status.Should().Be(LeadStatus.Scored);
    }

    [Fact]
    public async Task PlaceholderEmail_NoPhone_ScoresCold()
    {
        // completeness=0.5 (15) + source=12.5 + phone=0 + email_domain=0 + niche=7.5 + penalty=-5 = 30
        var lead = CreateEnriched("Maps Store", "store@maps.import");
        SetupRepos(lead);

        Score? saved = null;
        _scores.Setup(r => r.SaveAsync(It.IsAny<Score>(), It.IsAny<CancellationToken>()))
               .Callback<Score, CancellationToken>((s, _) => saved = s)
               .Returns(Task.CompletedTask);

        await _harness!.Bus.Publish(new LeadEnrichedMessage(lead.Id, null, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadEnrichedMessage>()).Should().BeTrue();

        saved!.Value.Should().BeLessThan(40);
        saved.Temperature.Should().Be(Temperature.Cold);
    }

    [Fact]
    public async Task InstagramBonus_CappedAt15()
    {
        // Base sem bônus: name+email (15) + source (12.5) + phone (15) + business_domain (15) + niche (7.5) = 65 (WARM)
        // Com instagram business (5) + 10k followers (8) + engagement 6% (5) = 18 → capped 15 → total 80 (HOT)
        var lead = CreateEnriched("Nail Studio", "nail@studio.com.br", phone: "11999999999");
        lead.SetInstagramData("nail_studio", null, 12_000, null, null, 6.0, "business", null);
        SetupRepos(lead);

        Score? saved = null;
        _scores.Setup(r => r.SaveAsync(It.IsAny<Score>(), It.IsAny<CancellationToken>()))
               .Callback<Score, CancellationToken>((s, _) => saved = s)
               .Returns(Task.CompletedTask);

        await _harness!.Bus.Publish(new LeadEnrichedMessage(lead.Id, null, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadEnrichedMessage>()).Should().BeTrue();

        // instagram breakdown não pode exceder 15
        var breakdown = System.Text.Json.JsonSerializer
            .Deserialize<Dictionary<string, double>>(saved!.BreakdownJson)!;
        breakdown["instagram"].Should().Be(15);
        saved.Value.Should().BeGreaterThanOrEqualTo(70);
    }

    [Fact]
    public async Task SourceMultiplier_AppliedCorrectly()
    {
        var source = Source.Create("paid_traffic", multiplier: 1.0);
        var lead = CreateEnriched("João", "joao@empresa.com", phone: "11999999999");
        lead.SetInstagramData(null, null, null, null, null, null, null, null);

        _leads.Setup(r => r.FindByIdAsync(lead.Id, It.IsAny<CancellationToken>())).ReturnsAsync(lead);
        _leads.Setup(r => r.SaveAsync(It.IsAny<Lead>(), It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);
        // source tem multiplier 1.0 — mas lead.SourceId é null, então fonte não é consultada
        _sources.Setup(r => r.FindByIdAsync(It.IsAny<Guid>(), It.IsAny<CancellationToken>())).ReturnsAsync(source);
        _niches.Setup(r => r.FindByIdAsync(It.IsAny<Guid>(), It.IsAny<CancellationToken>())).ReturnsAsync((Niche?)null);

        Score? saved = null;
        _scores.Setup(r => r.SaveAsync(It.IsAny<Score>(), It.IsAny<CancellationToken>()))
               .Callback<Score, CancellationToken>((s, _) => saved = s)
               .Returns(Task.CompletedTask);

        await _harness!.Bus.Publish(new LeadEnrichedMessage(lead.Id, null, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadEnrichedMessage>()).Should().BeTrue();

        // SourceId = null → fallback 0.5 → source_score = 12.5
        var breakdown = System.Text.Json.JsonSerializer
            .Deserialize<Dictionary<string, double>>(saved!.BreakdownJson)!;
        breakdown["source"].Should().Be(12.5);
    }
}
