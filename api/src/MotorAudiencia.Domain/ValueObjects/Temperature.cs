namespace MotorAudiencia.Domain.ValueObjects;

public static class Temperature
{
    public const string Hot = "HOT";
    public const string Warm = "WARM";
    public const string Cold = "COLD";

    public static string From(double score) =>
        score >= 70 ? Hot : score >= 40 ? Warm : Cold;
}
