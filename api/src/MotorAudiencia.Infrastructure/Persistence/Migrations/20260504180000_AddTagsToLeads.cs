using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace MotorAudiencia.Infrastructure.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class AddTagsToLeads : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "tags",
                table: "leads",
                type: "jsonb",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "tags",
                table: "leads");
        }
    }
}
