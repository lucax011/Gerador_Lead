using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using MotorAudiencia.Infrastructure.Persistence.Entities;

namespace MotorAudiencia.Infrastructure.Persistence.Configurations;

public sealed class RefreshTokenConfiguration : IEntityTypeConfiguration<RefreshTokenEntity>
{
    public void Configure(EntityTypeBuilder<RefreshTokenEntity> builder)
    {
        builder.ToTable("refresh_tokens");
        builder.HasKey(r => r.Id);
        builder.HasIndex(r => r.Token).IsUnique();
        builder.HasIndex(r => r.UserId);
        builder.Property(r => r.Token).IsRequired().HasMaxLength(200);
        builder.Ignore(r => r.IsExpired);
        builder.Ignore(r => r.IsActive);
    }
}
