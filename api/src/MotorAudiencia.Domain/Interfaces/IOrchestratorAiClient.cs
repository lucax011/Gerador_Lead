namespace MotorAudiencia.Domain.Interfaces;

public interface IOrchestratorAiClient
{
    Task<OrchestratorOutput> AnalyzeAsync(OrchestratorInput input, CancellationToken ct = default);
}
