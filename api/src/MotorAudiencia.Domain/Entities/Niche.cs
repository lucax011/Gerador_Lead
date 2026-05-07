namespace MotorAudiencia.Domain.Entities;

public sealed class Niche
{
    public Guid Id { get; private set; } = Guid.NewGuid();
    public string Name { get; private set; } = string.Empty;
    public double NicheScoreMultiplier { get; private set; } = 0.5;
    public DateTime CreatedAt { get; private set; } = DateTime.UtcNow;

    private Niche() { }

    public static Niche Create(string name, double multiplier = 0.5)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(name);
        if (multiplier is < 0 or > 1)
            throw new ArgumentOutOfRangeException(nameof(multiplier), "Deve estar entre 0 e 1.");
        return new Niche { Name = name.ToLowerInvariant(), NicheScoreMultiplier = multiplier };
    }
}
