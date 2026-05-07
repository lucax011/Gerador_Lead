using FluentAssertions;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Infrastructure.AI;

namespace MotorAudiencia.Tests.Consumers;

public sealed class DeterministicOrchestratorClientTests
{
    private readonly DeterministicOrchestratorClient _client = new();

    private static OrchestratorInput BuildInput(
        string temperature,
        string? phone = null,
        string? instagramUsername = null)
        => new(
            LeadId: Guid.NewGuid(),
            Name: "Test Lead",
            Phone: phone,
            InstagramUsername: instagramUsername,
            InstagramAccountType: null,
            InstagramFollowers: null,
            InstagramEngagementRate: null,
            CurrentScore: temperature == "HOT" ? 80.0 : temperature == "WARM" ? 55.0 : 20.0,
            Temperature: temperature,
            CampaignSlug: null,
            OfferDescription: null,
            IdealCustomerProfile: null,
            Ticket: null);

    [Fact]
    public async Task Cold_SemContato_RetornaNurture()
    {
        var input = BuildInput("COLD");
        var output = await _client.AnalyzeAsync(input);
        output.Approach.Should().Be("nurture");
        output.ScoreAdjustment.Should().Be(0);
    }

    [Fact]
    public async Task Hot_ComInstagram_RetornaInstagramDm()
    {
        var input = BuildInput("HOT", instagramUsername: "usuario_teste");
        var output = await _client.AnalyzeAsync(input);
        output.Approach.Should().Be("instagram_dm");
    }

    [Fact]
    public async Task Hot_ComTelefoneSemInstagram_RetornaWhatsapp()
    {
        var input = BuildInput("HOT", phone: "11999999999");
        var output = await _client.AnalyzeAsync(input);
        output.Approach.Should().Be("whatsapp");
    }

    [Fact]
    public async Task Warm_SemContato_RetornaNurture()
    {
        var input = BuildInput("WARM");
        var output = await _client.AnalyzeAsync(input);
        output.Approach.Should().Be("nurture");
    }
}
