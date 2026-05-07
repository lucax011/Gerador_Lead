using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using MotorAudiencia.Domain.Entities;
using MotorAudiencia.Domain.ValueObjects;

namespace MotorAudiencia.Infrastructure.Persistence.Configurations;

public sealed class LeadConfiguration : IEntityTypeConfiguration<Lead>
{
    public void Configure(EntityTypeBuilder<Lead> builder)
    {
        builder.ToTable("leads");
        builder.HasKey(l => l.Id);

        builder.Property(l => l.Name).HasMaxLength(300).IsRequired();
        builder.Property(l => l.Email).HasMaxLength(300).IsRequired();
        builder.HasIndex(l => l.Email).IsUnique();

        builder.Property(l => l.Phone).HasMaxLength(50);
        builder.Property(l => l.Company).HasMaxLength(300);

        builder.Property(l => l.Status)
            .HasConversion(s => s.ToString(), s => Enum.Parse<LeadStatus>(s))
            .HasMaxLength(50)
            .IsRequired();

        builder.Property(l => l.InstagramUsername).HasMaxLength(150);
        builder.Property(l => l.InstagramBio).HasMaxLength(200);
        builder.Property(l => l.InstagramAccountType).HasMaxLength(50);
        builder.Property(l => l.InstagramProfileUrl).HasMaxLength(500);

        builder.Property(l => l.MetadataJson).HasColumnType("jsonb").HasColumnName("metadata");
        builder.Property(l => l.OfferTagsJson).HasColumnType("jsonb").HasColumnName("offer_tags");
        builder.Property(l => l.CnpjDataJson).HasColumnType("jsonb").HasColumnName("cnpj_data");
        builder.Property(l => l.TagsJson).HasColumnType("jsonb").HasColumnName("tags");

        builder.Ignore(l => l.Tags);
        builder.Property(l => l.PerfilResumido).HasMaxLength(2000);

        builder.Property(l => l.CreatedAt).IsRequired();
        builder.Property(l => l.UpdatedAt).IsRequired();
    }
}
