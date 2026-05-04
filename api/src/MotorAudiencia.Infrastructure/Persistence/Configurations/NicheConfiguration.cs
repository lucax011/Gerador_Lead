using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using MotorAudiencia.Domain.Entities;

namespace MotorAudiencia.Infrastructure.Persistence.Configurations;

public sealed class NicheConfiguration : IEntityTypeConfiguration<Niche>
{
    public void Configure(EntityTypeBuilder<Niche> builder)
    {
        builder.ToTable("niches");
        builder.HasKey(n => n.Id);
        builder.Property(n => n.Name).HasMaxLength(100).IsRequired();
        builder.HasIndex(n => n.Name).IsUnique();
        builder.Property(n => n.NicheScoreMultiplier).IsRequired();
        builder.Property(n => n.CreatedAt).IsRequired();
    }
}
