using FluentAssertions;
using MassTransit;
using MassTransit.Testing;
using Microsoft.Extensions.DependencyInjection;
using Moq;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Domain.Events;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Domain.ValueObjects;
using MotorAudiencia.Infrastructure.AI;
using MotorAudiencia.Infrastructure.Messaging.Consumers;

namespace MotorAudiencia.Tests.Consumers;

public sealed class OrchestratorConsumerTests : IAsyncLifetime
{
    private readonly Mock<ILeadRepository> _leads = new();
    private readonly Mock<IScoreRepository> _scores = new();
    private readonly Mock<ICampaignRepository> _campaigns = new();
    private ServiceProvider? _provider;
    private ITestHarness? _harness;

    public async Task InitializeAsync()
    {
        _provider = new ServiceCollection()
            .AddScoped<ILeadRepository>(_ => _leads.Object)
            .AddScoped<IScoreRepository>(_ => _scores.Object)
            .AddScoped<ICampaignRepository>(_ => _campaigns.Object)
            .AddScoped<IOrchestratorAiClient, DeterministicOrchestratorClient>()
            .AddMassTransitTestHarness(x => x.AddConsumer<OrchestratorConsumer>())
            .BuildServiceProvider(true);

        _harness = _provider.GetRequiredService<ITestHarness>();
        await _harness.Start();
    }

    public async Task DisposeAsync()
    {
        await _harness!.Stop();
        await _provider!.DisposeAsync();
    }

    private static Lead CreateScored(string name, string email, string? phone = null)
    {
        var lead = Lead.Create(name, email, phone);
        lead.AdvanceStatus(LeadStatus.Validated);
        lead.AdvanceStatus(LeadStatus.Deduplicated);
        lead.AdvanceStatus(LeadStatus.Enriched);
        lead.AdvanceStatus(LeadStatus.Scored);
        return lead;
    }

    private void SetupRepos(Lead lead, Score score, Campaign? campaign)
    {
        _leads.Setup(r => r.FindByIdAsync(lead.Id, It.IsAny<CancellationToken>())).ReturnsAsync(lead);
        _leads.Setup(r => r.SaveAsync(It.IsAny<Lead>(), It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);
        _scores.Setup(r => r.FindByLeadIdAsync(lead.Id, It.IsAny<CancellationToken>())).ReturnsAsync(score);
        _scores.Setup(r => r.SaveAsync(It.IsAny<Score>(), It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);
        _campaigns.Setup(r => r.FindByIdAsync(It.IsAny<Guid>(), It.IsAny<CancellationToken>())).ReturnsAsync(campaign);
    }

    [Fact]
    public async Task LeadNaoEncontrado_NaoPublicaEvento()
    {
        var id = Guid.NewGuid();
        _leads.Setup(r => r.FindByIdAsync(id, It.IsAny<CancellationToken>())).ReturnsAsync((Lead?)null);

        await _harness!.Bus.Publish(
            new LeadScoredMessage(id, null, 75.0, Temperature.Hot, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadScoredMessage>()).Should().BeTrue();

        (await _harness.Published.Any<LeadOrchestratedMessage>()).Should().BeFalse();
    }

    [Fact]
    public async Task ScoreNaoEncontrado_NaoPublicaEvento()
    {
        var lead = CreateScored("Maria", "maria@test.com");
        _leads.Setup(r => r.FindByIdAsync(lead.Id, It.IsAny<CancellationToken>())).ReturnsAsync(lead);
        _scores.Setup(r => r.FindByLeadIdAsync(lead.Id, It.IsAny<CancellationToken>())).ReturnsAsync((Score?)null);

        await _harness!.Bus.Publish(
            new LeadScoredMessage(lead.Id, null, 80.0, Temperature.Hot, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadScoredMessage>()).Should().BeTrue();

        (await _harness.Published.Any<LeadOrchestratedMessage>()).Should().BeFalse();
    }

    [Fact]
    public async Task LeadCold_SemCampanha_PublicaComNurture()
    {
        var lead = CreateScored("João", "joao@cold.com");
        var score = Score.Create(lead.Id, 30.0, Temperature.Cold, new Dictionary<string, double>());
        SetupRepos(lead, score, campaign: null);

        await _harness!.Bus.Publish(
            new LeadScoredMessage(lead.Id, null, 30.0, Temperature.Cold, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadScoredMessage>()).Should().BeTrue();

        var published = _harness.Published.Select<LeadOrchestratedMessage>().FirstOrDefault();
        published.Should().NotBeNull();
        published!.Context.Message.Approach.Should().Be("nurture");
        published.Context.Message.LeadId.Should().Be(lead.Id);
    }

    [Fact]
    public async Task LeadHot_ComInstagram_PublicaComInstagramDm()
    {
        var lead = CreateScored("Ana", "ana@beauty.com");
        lead.SetInstagramData("ana_beauty", null, 2000, null, null, null, "business", null);
        var score = Score.Create(lead.Id, 80.0, Temperature.Hot, new Dictionary<string, double>());
        SetupRepos(lead, score, campaign: null);

        await _harness!.Bus.Publish(
            new LeadScoredMessage(lead.Id, null, 80.0, Temperature.Hot, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadScoredMessage>()).Should().BeTrue();

        var msg = _harness.Published.Select<LeadOrchestratedMessage>().First().Context.Message;
        msg.Approach.Should().Be("instagram_dm");
    }

    [Fact]
    public async Task LeadHot_ComTelefone_PublicaComWhatsapp_EStatusOrchestratedNoLead()
    {
        var lead = CreateScored("Pedro", "pedro@serv.com", phone: "11999999999");
        var score = Score.Create(lead.Id, 75.0, Temperature.Hot, new Dictionary<string, double>());
        SetupRepos(lead, score, campaign: null);

        await _harness!.Bus.Publish(
            new LeadScoredMessage(lead.Id, null, 75.0, Temperature.Hot, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadScoredMessage>()).Should().BeTrue();

        var msg = _harness.Published.Select<LeadOrchestratedMessage>().First().Context.Message;
        msg.Approach.Should().Be("whatsapp");
        msg.FinalScore.Should().Be(75.0);
        lead.Status.Should().Be(LeadStatus.Orchestrated);
    }
}
