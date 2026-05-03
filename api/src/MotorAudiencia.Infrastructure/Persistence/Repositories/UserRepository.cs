using Microsoft.EntityFrameworkCore;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Domain.Interfaces;

namespace MotorAudiencia.Infrastructure.Persistence.Repositories;

public sealed class UserRepository(AppDbContext db) : IUserRepository
{
    public Task<User?> FindByUsernameAsync(string username, CancellationToken ct = default)
        => db.Users.FirstOrDefaultAsync(u => u.Username == username.ToLowerInvariant(), ct);

    public async Task<User?> FindByRefreshTokenAsync(string token, CancellationToken ct = default)
    {
        return await db.RefreshTokens
            .Where(r => r.Token == token)
            .Select(r => r.User)
            .FirstOrDefaultAsync(ct);
    }

    public async Task SaveAsync(User user, CancellationToken ct = default)
    {
        if (db.Entry(user).State == EntityState.Detached)
            db.Users.Add(user);
        await db.SaveChangesAsync(ct);
    }
}
