using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;
using MotorAudiencia.Application.DTOs;
using MotorAudiencia.Application.UseCases.Auth;

namespace MotorAudiencia.API.Controllers;

[ApiController]
[Route("auth")]
public sealed class AuthController(LoginUseCase login, RefreshTokenUseCase refresh) : ControllerBase
{
    [HttpPost("login")]
    [EnableRateLimiting("login")]
    public async Task<IActionResult> Login([FromBody] LoginRequest req, CancellationToken ct)
    {
        var result = await login.ExecuteAsync(req, ct);
        if (!result.IsSuccess)
            return Unauthorized(new { error = result.Error });

        var response = result.Value!;
        SetRefreshCookie(response.RefreshToken, response.RefreshExpiresAt);
        return Ok(new { accessToken = response.AccessToken, expiresAt = response.ExpiresAt });
    }

    [HttpPost("refresh")]
    public async Task<IActionResult> Refresh(CancellationToken ct)
    {
        var token = Request.Cookies["refresh_token"];
        if (string.IsNullOrEmpty(token)) return Unauthorized(new { error = "no_refresh_token" });

        var result = await refresh.ExecuteAsync(token, ct);
        if (!result.IsSuccess) return Unauthorized(new { error = result.Error });

        var (accessToken, newRefreshToken, refreshExpiresAt) = result.Value;
        SetRefreshCookie(newRefreshToken, refreshExpiresAt);
        return Ok(new { accessToken, expiresAt = DateTime.UtcNow.AddMinutes(15) });
    }

    [HttpPost("logout")]
    [Authorize]
    public IActionResult Logout()
    {
        Response.Cookies.Delete("refresh_token");
        return NoContent();
    }

    [HttpGet("me")]
    [Authorize]
    public IActionResult Me()
        => Ok(new { username = User.Identity?.Name });

    private void SetRefreshCookie(string token, DateTime expires)
        => Response.Cookies.Append("refresh_token", token, new CookieOptions
        {
            HttpOnly = true,
            Secure = true,
            SameSite = SameSiteMode.Strict,
            Expires = expires,
        });
}
