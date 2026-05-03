using MotorAudiencia.Domain.Interfaces;

namespace MotorAudiencia.API.Middleware;

public sealed class HmacAuthMiddleware(RequestDelegate next)
{
    public async Task InvokeAsync(HttpContext ctx, IHmacValidator validator)
    {
        if (ctx.Request.Path.StartsWithSegments("/internal"))
        {
            var timestamp = ctx.Request.Headers["X-Service-Timestamp"].FirstOrDefault() ?? "";
            var signature = ctx.Request.Headers["X-Service-Signature"].FirstOrDefault() ?? "";
            ctx.Request.EnableBuffering();
            using var reader = new StreamReader(ctx.Request.Body, leaveOpen: true);
            var body = await reader.ReadToEndAsync();
            ctx.Request.Body.Position = 0;

            if (!validator.IsValid(timestamp, body, signature))
            {
                ctx.Response.StatusCode = 401;
                await ctx.Response.WriteAsync("unauthorized");
                return;
            }
        }
        await next(ctx);
    }
}
