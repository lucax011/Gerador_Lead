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

public sealed class ValidatorConsumerTests : IAsyncLifetime
{
    private readonly Mock<ILeadRepository> _leads = new();
    private ServiceProvider? _provider;
    private ITestHarness? _harness;

    public async Task InitializeAsync()
    {
        _provider = new ServiceCollection()
            .AddScoped<ILeadRepository>(_ => _leads.Object)
            .AddMassTransitTestHarness(x => x.AddConsumer<ValidatorConsumer>())
            .BuildServiceProvider(true);

        _harness = _provider.GetRequiredService<ITestHarness>();
        await _harness.Start();
    }

    public async Task DisposeAsync()
    {
        await _harness!.Stop();
        await _provider!.DisposeAsync();
    }

    [Fact]
    public async Task ValidLead_AdvancesStatus_AndPublishesLeadValidated()
    {
        var lead = Lead.Create("João Barbeiro", "joao@empresa.com.br", phone: "11999999999");
        _leads.Setup(r => r.FindByIdAsync(lead.Id, It.IsAny<CancellationToken>())).ReturnsAsync(lead);
        _leads.Setup(r => r.SaveAsync(It.IsAny<Lead>(), It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);

        await _harness!.Bus.Publish(new LeadCapturedMessage(lead.Id, null, Guid.NewGuid().ToString()));

        (await _harness.Published.Any<LeadValidatedMessage>()).Should().BeTrue();
        lead.Status.Should().Be(LeadStatus.Validated);
    }

    [Fact]
    public async Task InvalidEmailFormat_RejectsLead()
    {
        var lead = Lead.Create("João", "nao-e-email");
        _leads.Setup(r => r.FindByIdAsync(lead.Id, It.IsAny<CancellationToken>())).ReturnsAsync(lead);
        _leads.Setup(r => r.SaveAsync(It.IsAny<Lead>(), It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);

        await _harness!.Bus.Publish(new LeadCapturedMessage(lead.Id, null, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadCapturedMessage>()).Should().BeTrue();

        lead.Status.Should().Be(LeadStatus.Rejected);
    }

    [Fact]
    public async Task DisposableDomain_RejectsLead()
    {
        var lead = Lead.Create("Maria Silva", "maria@mailinator.com");
        _leads.Setup(r => r.FindByIdAsync(lead.Id, It.IsAny<CancellationToken>())).ReturnsAsync(lead);
        _leads.Setup(r => r.SaveAsync(It.IsAny<Lead>(), It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);

        await _harness!.Bus.Publish(new LeadCapturedMessage(lead.Id, null, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadCapturedMessage>()).Should().BeTrue();

        lead.Status.Should().Be(LeadStatus.Rejected);
    }

    [Fact]
    public async Task NameTooShort_RejectsLead()
    {
        var lead = Lead.Create("A", "a@empresa.com");
        _leads.Setup(r => r.FindByIdAsync(lead.Id, It.IsAny<CancellationToken>())).ReturnsAsync(lead);
        _leads.Setup(r => r.SaveAsync(It.IsAny<Lead>(), It.IsAny<CancellationToken>())).Returns(Task.CompletedTask);

        await _harness!.Bus.Publish(new LeadCapturedMessage(lead.Id, null, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadCapturedMessage>()).Should().BeTrue();

        lead.Status.Should().Be(LeadStatus.Rejected);
    }

    [Fact]
    public async Task LeadNotFound_DoesNothing()
    {
        _leads.Setup(r => r.FindByIdAsync(It.IsAny<Guid>(), It.IsAny<CancellationToken>()))
              .ReturnsAsync((Lead?)null);

        await _harness!.Bus.Publish(new LeadCapturedMessage(Guid.NewGuid(), null, Guid.NewGuid().ToString()));
        (await _harness.Consumed.Any<LeadCapturedMessage>()).Should().BeTrue();

        _leads.Verify(r => r.SaveAsync(It.IsAny<Lead>(), It.IsAny<CancellationToken>()), Times.Never);
    }
}
