using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Domain.ValueObjects;

namespace MotorAudiencia.Infrastructure.AI;

public sealed class DeterministicOrchestratorClient : IOrchestratorAiClient
{
    public Task<OrchestratorOutput> AnalyzeAsync(OrchestratorInput input, CancellationToken ct = default)
    {
        var approach = DetermineApproach(input);
        var output = new OrchestratorOutput(
            Approach: approach,
            Tone: "direto",
            BestTime: "19h-21h",
            ScoreAdjustment: 0,
            OpeningMessage: $"Olá {input.Name}, temos uma proposta para você!",
            NeedIdentified: "sem análise de IA",
            OfferCategory: "desconhecido",
            Objections: []
        );
        return Task.FromResult(output);
    }

    private static string DetermineApproach(OrchestratorInput input)
    {
        if (input.Temperature == Temperature.Cold)
            return "nurture";
        if (!string.IsNullOrEmpty(input.InstagramUsername))
            return "instagram_dm";
        if (!string.IsNullOrEmpty(input.Phone))
            return "whatsapp";
        return "nurture";
    }
}
