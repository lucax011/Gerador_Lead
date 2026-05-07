using System.Text.RegularExpressions;
using Microsoft.Extensions.Logging;

namespace MotorAudiencia.Infrastructure.Http;

public interface ICnpjWsClient
{
    Task<string?> GetRawAsync(string cnpj, CancellationToken ct = default);
}

public sealed partial class CnpjWsClient(HttpClient http, ILogger<CnpjWsClient> logger) : ICnpjWsClient
{
    [GeneratedRegex(@"\D")]
    private static partial Regex NonDigitRegex();

    public async Task<string?> GetRawAsync(string cnpj, CancellationToken ct = default)
    {
        var digits = NonDigitRegex().Replace(cnpj, "");
        if (digits.Length != 14) return null;

        try
        {
            var response = await http.GetAsync($"/cnpj/{digits}", ct);
            if (!response.IsSuccessStatusCode)
            {
                logger.LogWarning("CnpjWs: status {Status} para CNPJ {Cnpj}", response.StatusCode, digits);
                return null;
            }
            return await response.Content.ReadAsStringAsync(ct);
        }
        catch (Exception ex)
        {
            logger.LogWarning("CnpjWs: erro ao consultar CNPJ {Cnpj}: {Message}", digits, ex.Message);
            return null;
        }
    }
}
