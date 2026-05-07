using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using MotorAudiencia.Domain.Entities;

namespace MotorAudiencia.Infrastructure.Persistence.Configurations;

public sealed class CampaignConfiguration : IEntityTypeConfiguration<Campaign>
{
    public void Configure(EntityTypeBuilder<Campaign> builder)
    {
        builder.ToTable("campaigns");
        builder.HasKey(c => c.Id);
        builder.Property(c => c.Name).HasMaxLength(300).IsRequired();
        builder.Property(c => c.Slug).HasMaxLength(200).IsRequired();
        builder.HasIndex(c => c.Slug).IsUnique();
        builder.Property(c => c.Status).HasMaxLength(50).IsRequired();
        builder.Property(c => c.OfferDescription).HasColumnName("offer_description").HasMaxLength(2000);
        builder.Property(c => c.IdealCustomerProfile).HasColumnName("ideal_customer_profile").HasMaxLength(2000);
        builder.Property(c => c.Ticket).HasMaxLength(200);
        builder.Property(c => c.IsActive).HasColumnName("is_active").IsRequired();
        builder.Property(c => c.CreatedAt).HasColumnName("created_at").IsRequired();
        builder.Ignore(c => c.KeywordsAlvo);
    }
}
