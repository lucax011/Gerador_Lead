using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using MotorAudiencia.Domain.Interfaces;

namespace MotorAudiencia.Infrastructure.AI;

public sealed class OpenAiOrchestratorClient(
    IHttpClientFactory httpFactory,
    IConfiguration config,
    ILogger<OpenAiOrchestratorClient> logger) : IOrchestratorAiClient
{
    private const string Model = "gpt-4o-mini";

    public async Task<OrchestratorOutput> AnalyzeAsync(OrchestratorInput input, CancellationToken ct = default)
    {
        var apiKey = config["OPENAI_API_KEY"]!;
        var client = httpFactory.CreateClient("openai");

        var systemPrompt =
            "Você é especialista em análise de compatibilidade entre leads e ofertas B2B brasileiras. " +
            "Retorne APENAS um JSON válido com os campos: approach (whatsapp|instagram_dm|nurture|none), " +
            "tone, best_time, score_adjustment (número entre -20 e +20), opening_message, " +
            "need_identified, offer_category, objections (array de strings).";

        var requestBody = new
        {
            model = Model,
            messages = new[]
            {
                new { role = "system", content = systemPrompt },
                new { role = "user", content = BuildPrompt(input) }
            },
            response_format = new { type = "json_object" }
        };

        using var request = new HttpRequestMessage(HttpMethod.Post, "v1/chat/completions")
        {
            Headers = { Authorization = new AuthenticationHeaderValue("Bearer", apiKey) },
            Content = JsonContent.Create(requestBody)
        };

        var response = await client.SendAsync(request, ct);
        response.EnsureSuccessStatusCode();

        var json = await response.Content.ReadAsStringAsync(ct);
        using var doc = JsonDocument.Parse(json);
        var content = doc.RootElement
            .GetProperty("choices")[0]
            .GetProperty("message")
            .GetProperty("content")
            .GetString()!;

        logger.LogDebug("OpenAI response para lead {LeadId}: {Content}", input.LeadId, content);
        return ParseOutput(content);
    }

    private static string BuildPrompt(OrchestratorInput input)
    {
        var sb = new StringBuilder();
        sb.AppendLine($"Lead: {input.Name}");
        sb.AppendLine($"Score atual: {input.CurrentScore:F0} ({input.Temperature})");

        if (!string.IsNullOrEmpty(input.Phone))
            sb.AppendLine($"Telefone: {input.Phone}");

        if (!string.IsNullOrEmpty(input.InstagramUsername))
        {
            sb.AppendLine($"Instagram: @{input.InstagramUsername} ({input.InstagramAccountType})");
            if (input.InstagramFollowers.HasValue)
                sb.AppendLine($"Seguidores: {input.InstagramFollowers}, Engajamento: {input.InstagramEngagementRate:F1}%");
        }

        if (!string.IsNullOrEmpty(input.OfferDescription))
        {
            sb.AppendLine($"\nOferta: {input.OfferDescription}");
            sb.AppendLine($"Perfil ideal: {input.IdealCustomerProfile}");
            sb.AppendLine($"Ticket: {input.Ticket}");
        }

        sb.AppendLine("\nAnalise a compatibilidade e retorne a decisão de orquestração em JSON.");
        return sb.ToString();
    }

    private static OrchestratorOutput ParseOutput(string json)
    {
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        string Get(string key, string fallback) =>
            root.TryGetProperty(key, out var p) ? p.GetString() ?? fallback : fallback;

        double GetDouble(string key, double fallback) =>
            root.TryGetProperty(key, out var p) && p.TryGetDouble(out var d) ? d : fallback;

        var objections = root.TryGetProperty("objections", out var objProp)
            ? objProp.Deserialize<string[]>() ?? []
            : [];

        return new OrchestratorOutput(
            Approach: Get("approach", "nurture"),
            Tone: Get("tone", "direto"),
            BestTime: Get("best_time", "19h-21h"),
            ScoreAdjustment: GetDouble("score_adjustment", 0),
            OpeningMessage: Get("opening_message", ""),
            NeedIdentified: Get("need_identified", ""),
            OfferCategory: Get("offer_category", ""),
            Objections: objections
        );
    }
}
