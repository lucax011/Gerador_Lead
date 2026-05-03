// Domain/Entities/Campaign.cs
namespace MotorAudiencia.Domain.Entities;

public sealed class Campaign
{
    public Guid Id { get; private set; } = Guid.NewGuid();
    public string Name { get; private set; } = string.Empty;
    public string Slug { get; private set; } = string.Empty;
    public string Status { get; private set; } = "draft";
    public string? OfferDescription { get; private set; }
    public string? IdealCustomerProfile { get; private set; }
    public string? Ticket { get; private set; }
    private List<string> _keywordsAlvo = [];
    public IReadOnlyList<string> KeywordsAlvo => _keywordsAlvo.AsReadOnly();
    public bool IsActive { get; private set; } = true;
    public DateTime CreatedAt { get; private set; } = DateTime.UtcNow;

    private Campaign() { }

    public static Campaign Create(string name, string slug)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        ArgumentException.ThrowIfNullOrWhiteSpace(slug);
        return new Campaign { Name = name, Slug = slug };
    }
}
