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
    public List<string> Tags { get; private set; } = [];
    public string? PerfilResumido { get; private set; }
    public DateTime CreatedAt { get; private set; } = DateTime.UtcNow;
    public DateTime UpdatedAt { get; private set; } = DateTime.UtcNow;

    private Lead() { }

    public static Lead Create(string name, string email, string? phone = null, string? company = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        ArgumentException.ThrowIfNullOrWhiteSpace(email);
        return new Lead { Name = name, Email = email.ToLowerInvariant(), Phone = phone, Company = company };
    }

    public void AdvanceStatus(LeadStatus next) => Status = next;
}
