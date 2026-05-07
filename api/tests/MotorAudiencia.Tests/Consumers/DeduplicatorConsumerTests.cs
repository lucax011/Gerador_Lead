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

public sealed class DeduplicatorConsumerTests : IAsyncLifetime
{
    private readonly Mock<ILeadRepository> _leads = new();
    private ServiceProvider? _provider;
    private ITestHarness? _harness;

    public async Task InitializeAsync()
    {
        _provider = new ServiceCollection()
            .AddScoped<ILeadRepository>(_ => _leads.Object)
            .AddMassTransitTestHarness(x => x.AddConsumer<DeduplicatorConsumer>())
            .BuildServiceProvider(true);

        _harness = _provider.GetRequiredService<ITestHarness>();
        await _harness.Start();
    }

    public async Task DisposeAsync()
    {
        await _harness!.Stop();
        await _provider!.DisposeAsync();
    }

    private static Lead CreateValidated(string name, string email, string? phone = null)
    {
        var lead = Lead.Create(name, email, phone);
        lead.AdvanceStatus(LeadStatus.Validated);
        return lead;
    }

    [Fact]
    public async Task UniqueLead_AdvancesStatus_AndPublishesLeadDeduplicated()
    {
        var lead = CreateValidated("João", "joao@empresa.com");
        _leads.Setup(r => r.FindByIdAsync(lead.Id, It.IsAny<CancellationToken>())).ReturnsAsync(lead);
        _leads.Setup(r => r.FindByEmailAsync(lead.Email, It.IsAny<CancellationToken>())).ReturnsAsync((Lead?)null);
        _leads.Setup(r => r.SaveAsync(It.IsAny<Lead>(), It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);

        await _harness!.Bus.Publish(new LeadValidatedMessage(lead.Id, null, Guid.NewGuid().ToString()));

        (await _harness.Published.Any<LeadDeduplicatedMessage>()).Should().BeTrue();
        lead.Status.Should().Be(LeadStatus.Deduplicated);
    }

    [Fact]
    public async Task DuplicateLead_RejectsIncoming_MergesIntoCanonical_ContinuesWithCanonicalId()
    {
        var incoming = CreateValidated("João S.", "joao@empresa.com", phone: "11999999999");
        var canonical = CreateValidated("João Silva", "joao@empresa.com");
        // Advance canonical beyond Validated (já estava no pipeline antes)
        canonical.AdvanceStatus(LeadStatus.Deduplicated);
        canonical.AdvanceStatus(LeadStatus.Enriched);
        canonical.AdvanceStatus(LeadStatus.Scored);

        _leads.Setup(r => r.FindByIdAsync(incoming.Id, It.IsAny<CancellationToken>())).ReturnsAsync(incoming);
        _leads.Setup(r => r.FindByEmailAsync(incoming.Email, It.IsAny<CancellationToken>())).ReturnsAsync(canonical);
        _leads.Setup(r => r.SaveAsync(It.IsAny<Lead>(), It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);

        await _harness!.Bus.Publish(new LeadValidatedMessage(incoming.Id, null, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadValidatedMessage>()).Should().BeTrue();

        incoming.Status.Should().Be(LeadStatus.Rejected);
        // phone do incoming foi mergeado no canonical
        canonical.Phone.Should().Be("11999999999");
        // mensagem publicada com o ID canônico
        (await _harness.Published.Any<LeadDeduplicatedMessage>(
            x => x.Context.Message.LeadId == canonical.Id)).Should().BeTrue();
    }

    [Fact]
    public async Task LeadNotFound_DoesNothing()
    {
        _leads.Setup(r => r.FindByIdAsync(It.IsAny<Guid>(), It.IsAny<CancellationToken>()))
              .ReturnsAsync((Lead?)null);

        await _harness!.Bus.Publish(new LeadValidatedMessage(Guid.NewGuid(), null, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadValidatedMessage>()).Should().BeTrue();

        _leads.Verify(r => r.SaveAsync(It.IsAny<Lead>(), It.IsAny<CancellationToken>()), Times.Never);
    }
}
