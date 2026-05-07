using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using MotorAudiencia.Domain.Entities;

namespace MotorAudiencia.Infrastructure.Persistence.Configurations;

public sealed class SourceConfiguration : IEntityTypeConfiguration<Source>
{
    public void Configure(EntityTypeBuilder<Source> builder)
    {
        builder.ToTable("sources");
        builder.HasKey(s => s.Id);
        builder.Property(s => s.Name).HasMaxLength(100).IsRequired();
        builder.HasIndex(s => s.Name).IsUnique();
        builder.Property(s => s.BaseScoreMultiplier).IsRequired();
        builder.Property(s => s.CreatedAt).IsRequired();
    }
}
