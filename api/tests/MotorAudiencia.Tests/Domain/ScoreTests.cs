using FluentAssertions;
using MotorAudiencia.Domain.Entities;

namespace MotorAudiencia.Tests.Domain;

public sealed class ScoreTests
{
    [Fact]
    public void Refine_AjustaValorERecalculaTemperatura()
    {
        var score = Score.Create(Guid.NewGuid(), 50.0, "WARM", new Dictionary<string, double>());

        score.Refine(+20.0, "lead com Instagram engajado");

        score.Value.Should().Be(70.0);
        score.Temperature.Should().Be("HOT");
        score.AiReason.Should().Be("lead com Instagram engajado");
        score.UpdatedAt.Should().NotBeNull();
    }

    [Fact]
    public void Refine_ClampaSuperior_NaoUltrassa100()
    {
        var score = Score.Create(Guid.NewGuid(), 95.0, "HOT", new Dictionary<string, double>());

        score.Refine(+20.0, "excelente fit");

        score.Value.Should().Be(100.0);
        score.Temperature.Should().Be("HOT");
    }

    [Fact]
    public void Refine_ClampaInferior_NaoBaixaDeZero()
    {
        var score = Score.Create(Guid.NewGuid(), 10.0, "COLD", new Dictionary<string, double>());

        score.Refine(-20.0, "dados insuficientes");

        score.Value.Should().Be(0.0);
        score.Temperature.Should().Be("COLD");
    }
}
