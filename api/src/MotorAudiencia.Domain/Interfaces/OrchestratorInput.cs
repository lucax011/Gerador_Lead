namespace MotorAudiencia.Domain.Interfaces;

public sealed record OrchestratorInput(
    Guid LeadId,
    string Name,
    string? Phone,
    string? InstagramUsername,
    string? InstagramAccountType,
    int? InstagramFollowers,
    double? InstagramEngagementRate,
    double CurrentScore,
    string Temperature,
    string? CampaignSlug,
    string? OfferDescription,
    string? IdealCustomerProfile,
    string? Ticket
);
