namespace MotorAudiencia.API.Middleware;

public sealed class SecurityHeadersMiddleware(RequestDelegate next)
{
    public async Task InvokeAsync(HttpContext ctx)
    {
        var h = ctx.Response.Headers;
        h["X-Frame-Options"] = "DENY";
        h["X-Content-Type-Options"] = "nosniff";
        h["Referrer-Policy"] = "no-referrer";
        h["Permissions-Policy"] = "geolocation=(), camera=()";
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains";
        h["Content-Security-Policy"] = "default-src 'self'";
        await next(ctx);
    }
}
