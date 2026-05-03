// Domain/ValueObjects/LeadStatus.cs
namespace MotorAudiencia.Domain.ValueObjects;

public enum LeadStatus
{
    Captured,
    Validated,
    Deduplicated,
    Enriched,
    Scored,
    Tagged,
    Orchestrated,
    Distributed,
    Contacted,
    Replied,
    Converted,
    Churned,
    Rejected,
}
