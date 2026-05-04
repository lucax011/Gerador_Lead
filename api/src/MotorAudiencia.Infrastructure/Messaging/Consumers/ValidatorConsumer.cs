using System.Text.RegularExpressions;
using MassTransit;
using Microsoft.Extensions.Logging;
using MotorAudiencia.Domain.Events;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Domain.ValueObjects;

namespace MotorAudiencia.Infrastructure.Messaging.Consumers;

public sealed partial class ValidatorConsumer(
    ILeadRepository leads,
    ILogger<ValidatorConsumer> logger) : IConsumer<LeadCapturedMessage>
{
    private static readonly HashSet<string> DisposableDomains = new(StringComparer.OrdinalIgnoreCase)
    {
        "mailinator.com", "guerrillamail.com", "tempmail.com", "throwam.com", "yopmail.com",
        "sharklasers.com", "guerrillamailblock.com", "temp-mail.io", "trashmail.com",
        "maildrop.cc", "dispostable.com", "mailnull.com", "spamgourmet.com",
    };

    [GeneratedRegex(@"^[^@\s]+@[^@\s]+\.[^@\s]+$", RegexOptions.IgnoreCase)]
    private static partial Regex EmailRegex();

    public async Task Consume(ConsumeContext<LeadCapturedMessage> context)
    {
        var msg = context.Message;
        var lead = await leads.FindByIdAsync(msg.LeadId, context.CancellationToken);

        if (lead is null)
        {
            logger.LogWarning("Validator: lead {LeadId} não encontrado", msg.LeadId);
            return;
        }

        var rejection = Validate(lead.Name, lead.Email);
        if (rejection is not null)
        {
            logger.LogInformation("Validator: lead {LeadId} rejeitado — {Reason}", msg.LeadId, rejection);
            lead.AdvanceStatus(LeadStatus.Rejected);
            await leads.SaveAsync(lead, context.CancellationToken);
            return;
        }

        lead.AdvanceStatus(LeadStatus.Validated);
        await leads.SaveAsync(lead, context.CancellationToken);

        await context.Publish(
            new LeadValidatedMessage(msg.LeadId, msg.CampaignId, msg.CorrelationId),
            context.CancellationToken);

        logger.LogInformation("Validator: lead {LeadId} validado", msg.LeadId);
    }

    private static string? Validate(string name, string email)
    {
        if (string.IsNullOrWhiteSpace(name) || name.Trim().Length < 2)
            return "nome inválido";

        if (!EmailRegex().IsMatch(email))
            return "formato de email inválido";

        var domain = email.Split('@', 2).Last();
        if (DisposableDomains.Contains(domain))
            return $"domínio descartável: {domain}";

        return null;
    }
}
