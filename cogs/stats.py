import discord
from discord.ext import commands, tasks
from discord import app_commands

class StatsChannels(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_stats.start()

    def cog_unload(self):
        self.update_stats.cancel()

    async def get_or_create_category(self, guild: discord.Guild) -> discord.CategoryChannel:
        for cat in guild.categories:
            if "SERVER STATS" in cat.name.upper():
                return cat
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True),
            guild.me: discord.PermissionOverwrite(manage_channels=True, connect=True),
        }
        return await guild.create_category("✨ SERVER STATS ✨", overwrites=overwrites)

    async def get_or_create_channel(self, guild: discord.Guild, label: str, full_name: str) -> discord.VoiceChannel:
        category = await self.get_or_create_category(guild)
        for ch in category.voice_channels:
            if ch.name.startswith(label):
                return ch
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=False),
        }
        return await guild.create_voice_channel(
            name=full_name,
            category=category,
            overwrites=overwrites,
            reason="Stats channel setup",
        )

    @tasks.loop(minutes=5)
    async def update_stats(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            try:
                total = guild.member_count or 0
                bots = sum(1 for m in guild.members if m.bot)
                humans = total - bots
                boosts = guild.premium_subscription_count

                channels = [
                    ("✨ All Members", f"✨ All Members: {total}"),
                    ("✨ Members", f"✨ Members: {humans}"),
                    ("✨ Bots", f"✨ Bots: {bots}"),
                    ("✨ Boosts", f"✨ Boosts: {boosts}"),
                ]

                for label, full_name in channels:
                    ch = await self.get_or_create_channel(guild, label, full_name)
                    if ch.name != full_name:
                        await ch.edit(name=full_name)

            except discord.Forbidden:
                continue
            except Exception as e:
                print(f"Stats update failed in {guild.name}: {e}")

    @update_stats.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="setupstats", description="Create or refresh the stats voice channels")
    @app_commands.checks.has_permissions(administrator=True)
    async def setupstats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.update_stats()
        await interaction.followup.send("Stats channels updated.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(StatsChannels(bot))