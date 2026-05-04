using MassTransit;
using Microsoft.Extensions.Logging;
using MotorAudiencia.Domain.Events;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Domain.ValueObjects;

namespace MotorAudiencia.Infrastructure.Messaging.Consumers;

public sealed class DeduplicatorConsumer(
    ILeadRepository leads,
    ILogger<DeduplicatorConsumer> logger) : IConsumer<LeadValidatedMessage>
{
    public async Task Consume(ConsumeContext<LeadValidatedMessage> context)
    {
        var msg = context.Message;
        var lead = await leads.FindByIdAsync(msg.LeadId, context.CancellationToken);

        if (lead is null)
        {
            logger.LogWarning("Deduplicator: lead {LeadId} não encontrado", msg.LeadId);
            return;
        }

        var existing = await leads.FindByEmailAsync(lead.Email, context.CancellationToken);

        if (existing is not null && existing.Id != lead.Id)
        {
            logger.LogInformation(
                "Deduplicator: lead {LeadId} é duplicata de {ExistingId} — mesclando",
                msg.LeadId, existing.Id);

            existing.MergeFrom(lead);
            lead.AdvanceStatus(LeadStatus.Rejected);

            await leads.SaveAsync(lead, context.CancellationToken);
            await leads.SaveAsync(existing, context.CancellationToken);

            // Continua o pipeline com o lead canônico (existente)
            await context.Publish(
                new LeadDeduplicatedMessage(existing.Id, existing.CampaignId, msg.CorrelationId),
                context.CancellationToken);
            return;
        }

        lead.AdvanceStatus(LeadStatus.Deduplicated);
        await leads.SaveAsync(lead, context.CancellationToken);

        await context.Publish(
            new LeadDeduplicatedMessage(msg.LeadId, msg.CampaignId, msg.CorrelationId),
            context.CancellationToken);

        logger.LogInformation("Deduplicator: lead {LeadId} deduplicado", msg.LeadId);
    }
}
