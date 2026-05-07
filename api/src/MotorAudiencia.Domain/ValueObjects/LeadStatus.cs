// Domain/ValueObjects/LeadStatus.cs
namespace MotorAudiencia.Domain.ValueObjects;

public enum LeadStatus
{
    Captured,
    Validated,
    Deduplicated,
    Enriched,
    Scored,
    Orchestrated,
    Distributed,
    Contacted,
    Replied,
    Converted,
    Churned,
    Rejected,
}
