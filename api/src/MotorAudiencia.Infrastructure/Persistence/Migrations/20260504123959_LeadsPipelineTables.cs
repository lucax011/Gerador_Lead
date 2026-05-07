using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace MotorAudiencia.Infrastructure.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class LeadsPipelineTables : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "leads",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Name = table.Column<string>(type: "character varying(300)", maxLength: 300, nullable: false),
                    Email = table.Column<string>(type: "character varying(300)", maxLength: 300, nullable: false),
                    Phone = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: true),
                    Company = table.Column<string>(type: "character varying(300)", maxLength: 300, nullable: true),
                    Status = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: false),
                    CampaignId = table.Column<Guid>(type: "uuid", nullable: true),
                    SourceId = table.Column<Guid>(type: "uuid", nullable: true),
                    NicheId = table.Column<Guid>(type: "uuid", nullable: true),
                    InstagramUsername = table.Column<string>(type: "character varying(150)", maxLength: 150, nullable: true),
                    InstagramBio = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: true),
                    InstagramFollowers = table.Column<int>(type: "integer", nullable: true),
                    InstagramFollowing = table.Column<int>(type: "integer", nullable: true),
                    InstagramPosts = table.Column<int>(type: "integer", nullable: true),
                    InstagramEngagementRate = table.Column<double>(type: "double precision", nullable: true),
                    InstagramAccountType = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: true),
                    InstagramProfileUrl = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: true),
                    metadata = table.Column<string>(type: "jsonb", nullable: true),
                    offer_tags = table.Column<string>(type: "jsonb", nullable: true),
                    cnpj_data = table.Column<string>(type: "jsonb", nullable: true),
                    PerfilResumido = table.Column<string>(type: "character varying(2000)", maxLength: 2000, nullable: true),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_leads", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "niches",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Name = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: false),
                    NicheScoreMultiplier = table.Column<double>(type: "double precision", nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_niches", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "scores",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    LeadId = table.Column<Guid>(type: "uuid", nullable: false),
                    Value = table.Column<double>(type: "double precision", nullable: false),
                    Temperature = table.Column<string>(type: "character varying(10)", maxLength: 10, nullable: false),
                    breakdown = table.Column<string>(type: "jsonb", nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_scores", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "sources",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Name = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: false),
                    BaseScoreMultiplier = table.Column<double>(type: "double precision", nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_sources", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_leads_Email",
                table: "leads",
                column: "Email",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_niches_Name",
                table: "niches",
                column: "Name",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_scores_LeadId",
                table: "scores",
                column: "LeadId",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_sources_Name",
                table: "sources",
                column: "Name",
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "leads");

            migrationBuilder.DropTable(
                name: "niches");

            migrationBuilder.DropTable(
                name: "scores");

            migrationBuilder.DropTable(
                name: "sources");
        }
    }
}
