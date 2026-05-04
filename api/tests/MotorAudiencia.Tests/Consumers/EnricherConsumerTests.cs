using FluentAssertions;
using MassTransit;
using MassTransit.Testing;
using Microsoft.Extensions.DependencyInjection;
using Moq;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Domain.Events;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Domain.ValueObjects;
using MotorAudiencia.Infrastructure.Http;
using MotorAudiencia.Infrastructure.Messaging.Consumers;

namespace MotorAudiencia.Tests.Consumers;

public sealed class EnricherConsumerTests : IAsyncLifetime
{
    private readonly Mock<ILeadRepository> _leads = new();
    private readonly Mock<ICnpjWsClient> _cnpj = new();
    private ServiceProvider? _provider;
    private ITestHarness? _harness;

    public async Task InitializeAsync()
    {
        _provider = new ServiceCollection()
            .AddScoped<ILeadRepository>(_ => _leads.Object)
            .AddScoped<ICnpjWsClient>(_ => _cnpj.Object)
            .AddMassTransitTestHarness(x => x.AddConsumer<EnricherConsumer>())
            .BuildServiceProvider(true);

        _harness = _provider.GetRequiredService<ITestHarness>();
        await _harness.Start();
    }

    public async Task DisposeAsync()
    {
        await _harness!.Stop();
        await _provider!.DisposeAsync();
    }

    private static Lead CreateDeduplicated(string name, string email)
    {
        var lead = Lead.Create(name, email);
        lead.AdvanceStatus(LeadStatus.Validated);
        lead.AdvanceStatus(LeadStatus.Deduplicated);
        return lead;
    }

    [Fact]
    public async Task LeadWithoutCnpj_EnrichesAndPublishes_WithoutCallingCnpjClient()
    {
        var lead = CreateDeduplicated("Salão Beleza", "salao@gmail.com");
        _leads.Setup(r => r.FindByIdAsync(lead.Id, It.IsAny<CancellationToken>())).ReturnsAsync(lead);
        _leads.Setup(r => r.SaveAsync(It.IsAny<Lead>(), It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);

        await _harness!.Bus.Publish(new LeadDeduplicatedMessage(lead.Id, null, Guid.NewGuid().ToString()));

        (await _harness.Published.Any<LeadEnrichedMessage>()).Should().BeTrue();
        lead.Status.Should().Be(LeadStatus.Enriched);
        _cnpj.Verify(c => c.GetRawAsync(It.IsAny<string>(), It.IsAny<CancellationToken>()), Times.Never);
    }

    [Fact]
    public async Task LeadWithCnpj_CallsClientAndSetsCnpjData()
    {
        const string cnpjRaw = """{"situacao_cadastral":"ATIVA","razao_social":"EMPRESA LTDA"}""";
        var lead = CreateDeduplicated("Empresa Ltda", "empresa@empresa.com");
        lead.SetMetadata(new Dictionary<string, string> { ["cnpj"] = "11222333000181" });

        _leads.Setup(r => r.FindByIdAsync(lead.Id, It.IsAny<CancellationToken>())).ReturnsAsync(lead);
        _leads.Setup(r => r.SaveAsync(It.IsAny<Lead>(), It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);
        _cnpj.Setup(c => c.GetRawAsync("11222333000181", It.IsAny<CancellationToken>())).ReturnsAsync(cnpjRaw);

        await _harness!.Bus.Publish(new LeadDeduplicatedMessage(lead.Id, null, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadDeduplicatedMessage>()).Should().BeTrue();

        lead.CnpjDataJson.Should().Be(cnpjRaw);
        lead.IsCnpjActive().Should().BeTrue();
        (await _harness.Published.Any<LeadEnrichedMessage>()).Should().BeTrue();
    }

    [Fact]
    public async Task CnpjClientReturnsNull_StillPublishesLeadEnriched()
    {
        var lead = CreateDeduplicated("Empresa", "empresa@empresa.com");
        lead.SetMetadata(new Dictionary<string, string> { ["cnpj"] = "00000000000000" });

        _leads.Setup(r => r.FindByIdAsync(lead.Id, It.IsAny<CancellationToken>())).ReturnsAsync(lead);
        _leads.Setup(r => r.SaveAsync(It.IsAny<Lead>(), It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);
        _cnpj.Setup(c => c.GetRawAsync(It.IsAny<string>(), It.IsAny<CancellationToken>())).ReturnsAsync((string?)null);

        await _harness!.Bus.Publish(new LeadDeduplicatedMessage(lead.Id, null, Guid.NewGuid().ToString()));

        (await _harness.Published.Any<LeadEnrichedMessage>()).Should().BeTrue();
        lead.CnpjDataJson.Should().BeNull();
    }
}
