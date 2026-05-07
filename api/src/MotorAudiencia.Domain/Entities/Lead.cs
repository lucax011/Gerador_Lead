using System.Text.Json;
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
    public Guid? SourceId { get; private set; }
    public Guid? NicheId { get; private set; }

    // Instagram
    public string? InstagramUsername { get; private set; }
    public string? InstagramBio { get; private set; }
    public int? InstagramFollowers { get; private set; }
    public int? InstagramFollowing { get; private set; }
    public int? InstagramPosts { get; private set; }
    public double? InstagramEngagementRate { get; private set; }
    public string? InstagramAccountType { get; private set; }
    public string? InstagramProfileUrl { get; private set; }

    // JSONB — serialized by entity, mapped as TEXT/JSONB in EF config
    public string? MetadataJson { get; private set; }
    public string? OfferTagsJson { get; private set; }
    public string? CnpjDataJson { get; private set; }

    public string? TagsJson { get; private set; }
    public IReadOnlyList<string> Tags =>
        string.IsNullOrEmpty(TagsJson)
            ? []
            : JsonSerializer.Deserialize<List<string>>(TagsJson) ?? [];
    public string? PerfilResumido { get; private set; }
    public DateTime CreatedAt { get; private set; } = DateTime.UtcNow;
    public DateTime UpdatedAt { get; private set; } = DateTime.UtcNow;

    private static readonly Dictionary<LeadStatus, LeadStatus[]> AllowedTransitions = new()
    {
        [LeadStatus.Captured]     = [LeadStatus.Validated, LeadStatus.Rejected],
        [LeadStatus.Validated]    = [LeadStatus.Deduplicated, LeadStatus.Rejected],
        [LeadStatus.Deduplicated] = [LeadStatus.Enriched, LeadStatus.Rejected],
        [LeadStatus.Enriched]     = [LeadStatus.Scored, LeadStatus.Rejected],
        [LeadStatus.Scored]       = [LeadStatus.Orchestrated, LeadStatus.Distributed, LeadStatus.Rejected],
        [LeadStatus.Orchestrated] = [LeadStatus.Distributed, LeadStatus.Rejected],
        [LeadStatus.Distributed]  = [LeadStatus.Contacted, LeadStatus.Rejected],
        [LeadStatus.Contacted]    = [LeadStatus.Replied, LeadStatus.Churned],
        [LeadStatus.Replied]      = [LeadStatus.Converted, LeadStatus.Churned],
        [LeadStatus.Converted]    = [],
        [LeadStatus.Churned]      = [],
        [LeadStatus.Rejected]     = [],
    };

    private Lead() { }

    public static Lead Create(
        string name,
        string email,
        string? phone = null,
        string? company = null,
        Guid? sourceId = null,
        Guid? campaignId = null,
        Guid? nicheId = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        ArgumentException.ThrowIfNullOrWhiteSpace(email);
        return new Lead
        {
            Name = name,
            Email = email.ToLowerInvariant(),
            Phone = phone,
            Company = company,
            SourceId = sourceId,
            CampaignId = campaignId,
            NicheId = nicheId,
        };
    }

    public void AdvanceStatus(LeadStatus next)
    {
        if (!AllowedTransitions.TryGetValue(Status, out var allowed) || !allowed.Contains(next))
            throw new InvalidOperationException($"Transição inválida: {Status} → {next}");
        Status = next;
        UpdatedAt = DateTime.UtcNow;
    }

    public void SetTags(IEnumerable<string> tags)
    {
        var list = tags.ToList();
        TagsJson = list.Count > 0 ? JsonSerializer.Serialize(list) : null;
        UpdatedAt = DateTime.UtcNow;
    }

    public void SetInstagramData(
        string? username, string? bio,
        int? followers, int? following, int? posts,
        double? engagementRate, string? accountType, string? profileUrl)
    {
        InstagramUsername = username;
        InstagramBio = bio;
        InstagramFollowers = followers;
        InstagramFollowing = following;
        InstagramPosts = posts;
        InstagramEngagementRate = engagementRate;
        InstagramAccountType = accountType;
        InstagramProfileUrl = profileUrl;
        UpdatedAt = DateTime.UtcNow;
    }

    public void SetCnpjData(string cnpjJson)
    {
        CnpjDataJson = cnpjJson;
        UpdatedAt = DateTime.UtcNow;
    }

    public void SetMetadata(Dictionary<string, string> metadata)
    {
        MetadataJson = JsonSerializer.Serialize(metadata);
        UpdatedAt = DateTime.UtcNow;
    }

    public string? GetMetadataValue(string key)
    {
        if (string.IsNullOrEmpty(MetadataJson)) return null;
        var dict = JsonSerializer.Deserialize<Dictionary<string, string>>(MetadataJson);
        return dict?.GetValueOrDefault(key);
    }

    public bool IsCnpjActive()
    {
        if (string.IsNullOrEmpty(CnpjDataJson)) return false;
        try
        {
            using var doc = JsonDocument.Parse(CnpjDataJson);
            return doc.RootElement.TryGetProperty("situacao_cadastral", out var prop)
                && prop.ValueKind == JsonValueKind.String
                && prop.GetString()?.Equals("ATIVA", StringComparison.OrdinalIgnoreCase) == true;
        }
        catch { return false; }
    }

    public void MergeFrom(Lead other)
    {
        if (string.IsNullOrEmpty(Phone) && !string.IsNullOrEmpty(other.Phone))
            Phone = other.Phone;
        if (string.IsNullOrEmpty(Company) && !string.IsNullOrEmpty(other.Company))
            Company = other.Company;
        if (InstagramFollowers is null && other.InstagramFollowers is not null)
            SetInstagramData(
                other.InstagramUsername, other.InstagramBio,
                other.InstagramFollowers, other.InstagramFollowing, other.InstagramPosts,
                other.InstagramEngagementRate, other.InstagramAccountType, other.InstagramProfileUrl);
        UpdatedAt = DateTime.UtcNow;
    }
}
