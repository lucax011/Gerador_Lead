namespace MotorAudiencia.Domain.Events;

public sealed record LeadCapturedMessage(
    Guid LeadId,
    Guid? CampaignId,
    string CorrelationId);
