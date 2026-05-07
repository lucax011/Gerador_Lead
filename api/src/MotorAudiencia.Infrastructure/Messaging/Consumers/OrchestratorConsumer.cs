using MassTransit;
using Microsoft.Extensions.Logging;
using MotorAudiencia.Domain.Events;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Domain.ValueObjects;

namespace MotorAudiencia.Infrastructure.Messaging.Consumers;

public sealed class OrchestratorConsumer(
    ILeadRepository leads,
    IScoreRepository scores,
    ICampaignRepository campaigns,
    IOrchestratorAiClient aiClient,
    ILogger<OrchestratorConsumer> logger) : IConsumer<LeadScoredMessage>
{
    public async Task Consume(ConsumeContext<LeadScoredMessage> context)
    {
        var msg = context.Message;

        var lead = await leads.FindByIdAsync(msg.LeadId, context.CancellationToken);
        if (lead is null)
        {
            logger.LogWarning("Orchestrator: lead {LeadId} não encontrado", msg.LeadId);
            return;
        }

        var score = await scores.FindByLeadIdAsync(msg.LeadId, context.CancellationToken);
        if (score is null)
        {
            logger.LogWarning("Orchestrator: score para lead {LeadId} não encontrado", msg.LeadId);
            return;
        }

        var campaign = msg.CampaignId.HasValue
            ? await campaigns.FindByIdAsync(msg.CampaignId.Value, context.CancellationToken)
            : null;

        var input = new OrchestratorInput(
            LeadId: lead.Id,
            Name: lead.Name,
            Phone: lead.Phone,
            InstagramUsername: lead.InstagramUsername,
            InstagramAccountType: lead.InstagramAccountType,
            InstagramFollowers: lead.InstagramFollowers,
            InstagramEngagementRate: lead.InstagramEngagementRate,
            CurrentScore: score.Value,
            Temperature: score.Temperature,
            CampaignSlug: campaign?.Slug,
            OfferDescription: campaign?.OfferDescription,
            IdealCustomerProfile: campaign?.IdealCustomerProfile,
            Ticket: campaign?.Ticket
        );

        var output = await aiClient.AnalyzeAsync(input, context.CancellationToken);

        score.Refine(output.ScoreAdjustment, output.NeedIdentified);
        await scores.SaveAsync(score, context.CancellationToken);

        lead.AdvanceStatus(LeadStatus.Orchestrated);
        await leads.SaveAsync(lead, context.CancellationToken);

        await context.Publish(
            new LeadOrchestratedMessage(
                LeadId: lead.Id,
                CampaignId: msg.CampaignId,
                Approach: output.Approach,
                Tone: output.Tone,
                BestTime: output.BestTime,
                OpeningMessage: output.OpeningMessage,
                FinalScore: score.Value,
                CorrelationId: msg.CorrelationId),
            context.CancellationToken);

        logger.LogInformation(
            "Orchestrator: lead {LeadId} → approach={Approach} score={Score:F1}",
            lead.Id, output.Approach, score.Value);
    }
}
