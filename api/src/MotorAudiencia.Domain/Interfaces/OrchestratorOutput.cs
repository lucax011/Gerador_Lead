namespace MotorAudiencia.Domain.Interfaces;

public sealed record OrchestratorOutput(
    string Approach,
    string Tone,
    string BestTime,
    double ScoreAdjustment,
    string OpeningMessage,
    string NeedIdentified,
    string OfferCategory,
    string[] Objections
);
