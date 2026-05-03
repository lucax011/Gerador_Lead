using Microsoft.EntityFrameworkCore;
using MotorAudiencia.Domain.Interfaces;
using MotorAudiencia.Infrastructure.Persistence.Entities;

namespace MotorAudiencia.Infrastructure.Persistence.Repositories;

public sealed class RefreshTokenRepository(AppDbContext db) : IRefreshTokenRepository
{
    public async Task<RefreshTokenInfo?> FindByTokenAsync(string token, CancellationToken ct = default)
    {
        var entity = await db.RefreshTokens.FirstOrDefaultAsync(r => r.Token == token, ct);
        return entity is null ? null : ToInfo(entity);
    }

    public async Task AddAsync(RefreshTokenResult token, CancellationToken ct = default)
    {
        db.RefreshTokens.Add(new RefreshTokenEntity
        {
            Token = token.Token,
            FamilyId = token.FamilyId,
            UserId = token.UserId,
            ExpiresAt = token.ExpiresAt,
        });
        await db.SaveChangesAsync(ct);
    }

    public async Task RevokeAsync(string token, CancellationToken ct = default)
    {
        var entity = await db.RefreshTokens.FirstOrDefaultAsync(r => r.Token == token, ct);
        if (entity is not null)
        {
            entity.IsRevoked = true;
            await db.SaveChangesAsync(ct);
        }
    }

    public async Task RevokeAllByFamilyAsync(Guid familyId, CancellationToken ct = default)
    {
        await db.RefreshTokens
            .Where(r => r.FamilyId == familyId)
            .ExecuteUpdateAsync(s => s.SetProperty(r => r.IsRevoked, true), ct);
    }

    private static RefreshTokenInfo ToInfo(RefreshTokenEntity e) =>
        new(e.Token, e.FamilyId, e.UserId, e.ExpiresAt, e.IsRevoked);
}
