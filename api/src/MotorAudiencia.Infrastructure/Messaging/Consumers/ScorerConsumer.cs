using MassTransit;
using Microsoft.Extensions.Logging;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Domain.Events;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Domain.ValueObjects;

namespace MotorAudiencia.Infrastructure.Messaging.Consumers;

public sealed class ScorerConsumer(
    ILeadRepository leads,
    ISourceRepository sources,
    INicheRepository niches,
    IScoreRepository scores,
    ILogger<ScorerConsumer> logger) : IConsumer<LeadEnrichedMessage>
{
    private static readonly HashSet<string> FreeEmailDomains = new(StringComparer.OrdinalIgnoreCase)
    {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com",
        "icloud.com", "me.com", "mac.com", "protonmail.com", "uol.com.br",
        "bol.com.br", "ig.com.br", "terra.com.br", "globomail.com", "r7.com",
    };

    public async Task Consume(ConsumeContext<LeadEnrichedMessage> context)
    {
        var msg = context.Message;
        var lead = await leads.FindByIdAsync(msg.LeadId, context.CancellationToken);

        if (lead is null)
        {
            logger.LogWarning("Scorer: lead {LeadId} não encontrado", msg.LeadId);
            return;
        }

        var source = lead.SourceId.HasValue
            ? await sources.FindByIdAsync(lead.SourceId.Value, context.CancellationToken)
            : null;

        var niche = lead.NicheId.HasValue
            ? await niches.FindByIdAsync(lead.NicheId.Value, context.CancellationToken)
            : null;

        var (value, breakdown) = Calculate(lead, source, niche);
        var temperature = Temperature.From(value);

        var score = Score.Create(lead.Id, value, temperature, breakdown);
        await scores.SaveAsync(score, context.CancellationToken);

        lead.AdvanceStatus(LeadStatus.Scored);
        await leads.SaveAsync(lead, context.CancellationToken);

        await context.Publish(
            new LeadScoredMessage(msg.LeadId, msg.CampaignId, value, temperature, msg.CorrelationId),
            context.CancellationToken);

        logger.LogInformation(
            "Scorer: lead {LeadId} score={Score:F1} temperatura={Temp}",
            msg.LeadId, value, temperature);
    }

    private static (double value, Dictionary<string, double> breakdown) Calculate(
        Lead lead, Source? source, Niche? niche)
    {
        var bd = new Dictionary<string, double>();
        double score = 0;

        // 1. Data completeness (0–30)
        bd["data_completeness"] = Math.Round(ComputeCompleteness(lead) * 30, 2);
        score += bd["data_completeness"];

        // 2. Source multiplier (0–25)
        bd["source"] = Math.Round((source?.BaseScoreMultiplier ?? 0.5) * 25, 2);
        score += bd["source"];

        // 3. Phone present (0–15)
        bd["phone"] = string.IsNullOrEmpty(lead.Phone) ? 0 : 15;
        score += bd["phone"];

        // 4. Email domain quality (0–15)
        bd["email_domain"] = EmailDomainScore(lead.Email);
        score += bd["email_domain"];

        // 5. Niche match (0–15)
        bd["niche_match"] = Math.Round((niche?.NicheScoreMultiplier ?? 0.5) * 15, 2);
        score += bd["niche_match"];

        // 6. Instagram bonuses (capped at +15)
        bd["instagram"] = InstagramBonus(lead);
        score += bd["instagram"];

        // 7. CNPJ ativo (+5)
        if (lead.IsCnpjActive())
        {
            bd["cnpj"] = 5;
            score += 5;
        }

        // 8. Email placeholder (–5)
        if (IsPlaceholderEmail(lead.Email))
        {
            bd["email_penalty"] = -5;
            score += -5;
        }

        return (Math.Clamp(Math.Round(score, 2), 0, 100), bd);
    }

    private static double ComputeCompleteness(Lead lead)
    {
        double filled = 0;
        const double total = 4.0;
        if (!string.IsNullOrWhiteSpace(lead.Name)) filled += 1;
        if (!string.IsNullOrWhiteSpace(lead.Email)) filled += 1;
        if (!string.IsNullOrWhiteSpace(lead.Phone)) filled += 1;
        if (!string.IsNullOrWhiteSpace(lead.Company)) filled += 0.5;
        if (!string.IsNullOrWhiteSpace(lead.InstagramUsername)) filled += 0.5;
        return Math.Min(filled / total, 1.0);
    }

    private static double EmailDomainScore(string email)
    {
        if (IsPlaceholderEmail(email)) return 0;
        var domain = email.Split('@', 2).LastOrDefault() ?? string.Empty;
        return FreeEmailDomains.Contains(domain) ? 8 : 15;
    }

    private static bool IsPlaceholderEmail(string email) =>
        email.Contains("@maps.import", StringComparison.OrdinalIgnoreCase)
        || email.Contains("placeholder", StringComparison.OrdinalIgnoreCase);

    private static double InstagramBonus(Lead lead)
    {
        double bonus = 0;

        bonus += lead.InstagramAccountType?.ToLowerInvariant() switch
        {
            "business" => 5,
            "creator"  => 3,
            _          => 0,
        };

        bonus += lead.InstagramFollowers switch
        {
            >= 10_000 => 8,
            >= 1_000  => 4,
            >= 500    => 2,
            _         => 0,
        };

        bonus += lead.InstagramEngagementRate switch
        {
            >= 5.0 => 5,
            >= 3.0 => 3,
            _      => 0,
        };

        return Math.Min(bonus, 15);
    }
}
