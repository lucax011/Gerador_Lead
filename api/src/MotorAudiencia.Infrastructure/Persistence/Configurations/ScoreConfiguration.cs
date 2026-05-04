using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using MotorAudiencia.Domain.Entities;

namespace MotorAudiencia.Infrastructure.Persistence.Configurations;

public sealed class ScoreConfiguration : IEntityTypeConfiguration<Score>
{
    public void Configure(EntityTypeBuilder<Score> builder)
    {
        builder.ToTable("scores");
        builder.HasKey(s => s.Id);
        builder.HasIndex(s => s.LeadId).IsUnique();
        builder.Property(s => s.Value).IsRequired();
        builder.Property(s => s.Temperature).HasMaxLength(10).IsRequired();
        builder.Property(s => s.BreakdownJson).HasColumnType("jsonb").HasColumnName("breakdown").IsRequired();
        builder.Property(s => s.CreatedAt).IsRequired();
    }
}
