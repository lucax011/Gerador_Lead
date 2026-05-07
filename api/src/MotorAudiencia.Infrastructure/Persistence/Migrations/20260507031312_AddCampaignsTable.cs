using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace MotorAudiencia.Infrastructure.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class AddCampaignsTable : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "campaigns",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    Name = table.Column<string>(type: "character varying(300)", maxLength: 300, nullable: false),
                    Slug = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: false),
                    Status = table.Column<string>(type: "character varying(50)", maxLength: 50, nullable: false),
                    offer_description = table.Column<string>(type: "character varying(2000)", maxLength: 2000, nullable: true),
                    ideal_customer_profile = table.Column<string>(type: "character varying(2000)", maxLength: 2000, nullable: true),
                    Ticket = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: true),
                    is_active = table.Column<bool>(type: "boolean", nullable: false),
                    created_at = table.Column<DateTime>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_campaigns", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_campaigns_Slug",
                table: "campaigns",
                column: "Slug",
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "campaigns");
        }
    }
}
