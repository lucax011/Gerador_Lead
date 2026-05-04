using MassTransit;
using Microsoft.Extensions.Logging;
using MotorAudiencia.Domain.Events;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Domain.ValueObjects;
using MotorAudiencia.Infrastructure.Http;

namespace MotorAudiencia.Infrastructure.Messaging.Consumers;

public sealed class EnricherConsumer(
    ILeadRepository leads,
    ICnpjWsClient cnpjClient,
    ILogger<EnricherConsumer> logger) : IConsumer<LeadDeduplicatedMessage>
{
    public async Task Consume(ConsumeContext<LeadDeduplicatedMessage> context)
    {
        var msg = context.Message;
        var lead = await leads.FindByIdAsync(msg.LeadId, context.CancellationToken);

        if (lead is null)
        {
            logger.LogWarning("Enricher: lead {LeadId} não encontrado", msg.LeadId);
            return;
        }

        var cnpj = lead.GetMetadataValue("cnpj");
        if (!string.IsNullOrEmpty(cnpj))
        {
            var cnpjJson = await cnpjClient.GetRawAsync(cnpj, context.CancellationToken);
            if (cnpjJson is not null)
            {
                lead.SetCnpjData(cnpjJson);
                logger.LogInformation("Enricher: CNPJ enriquecido para lead {LeadId}", msg.LeadId);
            }
        }

        lead.AdvanceStatus(LeadStatus.Enriched);
        await leads.SaveAsync(lead, context.CancellationToken);

        await context.Publish(
            new LeadEnrichedMessage(msg.LeadId, msg.CampaignId, msg.CorrelationId),
            context.CancellationToken);

        logger.LogInformation("Enricher: lead {LeadId} enriquecido", msg.LeadId);
    }
}
