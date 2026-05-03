// Domain/Entities/Lead.cs
using MotorAudiencia.Domain.ValueObjects;

namespace MotorAudiencia.Domain.Entities;

public sealed class Lead
{
    public Guid Id { get; private set; } = Guid.NewGuid();
    public string Name { get; private set; } = string.Empty;
    public string Email { get; private set; } = string.Empty;
    public string? Phone { get; private set; }
    public string? Company { get; private set; }
    public LeadStatus Status { get; private set; } = LeadStatus.Captured;
    public Guid? CampaignId { get; private set; }
    private List<string> _tags = [];
    public IReadOnlyList<string> Tags => _tags.AsReadOnly();
    public string? PerfilResumido { get; private set; }
    public DateTime CreatedAt { get; private set; } = DateTime.UtcNow;
    public DateTime UpdatedAt { get; private set; } = DateTime.UtcNow;

    private static readonly Dictionary<LeadStatus, LeadStatus[]> AllowedTransitions = new()
    {
        [LeadStatus.Captured]     = [LeadStatus.Validated, LeadStatus.Rejected],
        [LeadStatus.Validated]    = [LeadStatus.Deduplicated, LeadStatus.Rejected],
        [LeadStatus.Deduplicated] = [LeadStatus.Enriched, LeadStatus.Rejected],
        [LeadStatus.Enriched]     = [LeadStatus.Scored, LeadStatus.Rejected],
        [LeadStatus.Scored]       = [LeadStatus.Tagged, LeadStatus.Distributed, LeadStatus.Rejected],
        [LeadStatus.Tagged]       = [LeadStatus.Orchestrated, LeadStatus.Rejected],
        [LeadStatus.Orchestrated] = [LeadStatus.Distributed, LeadStatus.Rejected],
        [LeadStatus.Distributed]  = [LeadStatus.Contacted, LeadStatus.Rejected],
        [LeadStatus.Contacted]    = [LeadStatus.Replied, LeadStatus.Churned],
        [LeadStatus.Replied]      = [LeadStatus.Converted, LeadStatus.Churned],
        [LeadStatus.Converted]    = [],
        [LeadStatus.Churned]      = [],
        [LeadStatus.Rejected]     = [],
    };

    private Lead() { }

    public static Lead Create(string name, string email, string? phone = null, string? company = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        ArgumentException.ThrowIfNullOrWhiteSpace(email);
        return new Lead { Name = name, Email = email.ToLowerInvariant(), Phone = phone, Company = company };
    }

    public void AdvanceStatus(LeadStatus next)
    {
        if (!AllowedTransitions.TryGetValue(Status, out var allowed) || !allowed.Contains(next))
            throw new InvalidOperationException($"Invalid transition: {Status} → {next}");
        Status = next;
    }

    public void SetTags(IEnumerable<string> tags)
    {
        _tags = [..tags];
        UpdatedAt = DateTime.UtcNow;
    }
}
