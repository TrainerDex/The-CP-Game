from redbot.core import commands, Config, checks
import requests
import pyocr
import pyocr.builders
from PIL import Image
from io import BytesIO
import re

class CPGame:
    """The CP Game"""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier='com.trainerdex.cpgame')
        #self.config.register_channel(
        #    active=False,
        #    start=None,
        #    number=None,
        #    last_trainer_id=None,
        #    timeout=None
        #)
    
    @commands.command(name="number")
    async def check_number(self, ctx):
        channel_config = self.config.channel(channel=ctx.channel)
        if await channel_config.active():
            await ctx.send(f"The next number is {await channel_config.number()}.")
        else:
            await ctx.send(f"There is no live game on.")
    
    @checks.mod_or_permissions(manage_channels=True)
    @commands.command(name="start", case_insensitive=True)
    async def start_game(self, ctx, start: int=10):
        """Start the game in this channel from that number. It's highly recommended to use a dedicated channel for this as any other message will be deleted."""
        if not 10 <= start < 3500:
            return await ctx.send("The CP game can only start on a number between 10 and 3500.")
        
        await ctx.send(f"Creating a new game starting at CP{start}.")
        channel_config = self.config.channel(channel=ctx.channel)
        await channel_config.active.set(True)
        await channel_config.start.set(start)
        await channel_config.number.set(start)
        await channel_config.last_trainer_id.set(None)
    
    @checks.mod_or_permissions(manage_channels=True)
    @commands.command(name="pause", case_insensitive=True)
    async def pause_game(self, ctx):
        """Pause the CP Game"""
    
        channel_config = self.config.channel(channel=ctx.channel)
        if await channel_config.start() and await channel_config.number():
            await ctx.send("Pausing active game.")
            await channel_config.active.set(False)
        elif await channel_config.active():
            await channel_config.active.set(False)
            await channel_config.start.set(None)
            await channel_config.number.set(None)
            await channel_config.last_trainer_id.set(None)
            await ctx.send("There is an issue with your pausing your current game, all progress has been lost.")
        else:
            await ctx.send("No active game! Nothing to do.")
    
    @checks.mod_or_permissions(manage_channels=True)
    @commands.command(name="continue", case_insensitive=True)
    async def continue_game(self, ctx):
        """Continute an already started game"""
    
        channel_config = self.config.channel(channel=ctx.channel)
        if await channel_config.start() and await channel_config.number():
            active_number = await channel_config.number()
            await ctx.send(f"Continuing active game, the next number is {active_number}.")
            await channel_config.active.set(True)
        else:
            await ctx.send("No valid game! Please use the `start` command to create a new game.")
    
    @checks.mod_or_permissions(manage_channels=True)
    @commands.command(name="end", case_insensitive=True)
    async def end_game(self, ctx):
        """End the existing game"""
        channel_config = self.config.channel(channel=ctx.channel)
        if await channel_config.start() and await channel_config.number():
            start = await channel_config.start()
            last_number = await channel_config.number()-1
            end_goal = 3500
            completion = (last_number-start)/(end_goal-start)
            if completion < 0:
                completion = 0.0
            if completion < 0.10:
                rank_comment = "What a futile attempt."
            elif 0.10 <= completion < 0.50:
                rank_comment = "You gave it a good go!"
            elif 0.50 <= completion < 0.85:
                rank_comment = "Sorry to see you giving up so close to the end."
            elif 0.85 <= completion < 1:
                rank_comment = "You're just a hair away and you're giving up. You must be Instinct."
            elif 1 < completion:
                rank_comment = "You made it over 100%? What is this black magic."
            else:
                rank_comment = ""
            await ctx.send(f"Ending game. All progress will be lost.\nYou completed {completion:.0%}! {rank_comment}")
        else:
            await ctx.send("No valid game to end.")
            await channel_config.active.set(False)
    
    async def on_message(self, message):
        channel_config = self.config.channel(channel=message.channel)
        ctx = await self.bot.get_context(message)
        if not await channel_config.active():
            return
        
        if message.author.bot:
            return
        
        if ctx.valid:
            return
        
        if len(message.attachments) != 1:
            await message.delete()
            return
        
        if len(message.attachments) == 1:
            image = requests.get(message.attachments[0].url).content
            if message.author.id == await channel_config.last_trainer_id():
                await message.delete()
                await ctx.send(f"Deleted a screenshot by {message.author.mention} as the last submission was submitted by them.", delete_after=30)
                return
            cp = ScanImage(image).cp
            if cp is None:
                await message.delete()
                await ctx.send(f"Deleted a screenshot by {message.author.mention} as the CP couldn't be detected.", delete_after=30)
                return
            print(cp)
            need = await channel_config.number()
            if cp != need:
                await message.delete()
                await ctx.send(f"Deleted screenshot by {message.author.mention} as we're looking for CP{need} not CP{cp}.", delete_after=30)
                return
            else:
                await message.add_reaction("👍")
                if need != 3500:
                    await channel_config.number.set(need+1)
                    await channel_config.last_trainer_id.set(message.author.id)
                else:
                    await ctx.send(f"Well done {message.author.mention}, <@{await channel_config.last_trainer_id()}> and company, you completed The CP Game")
                    await channel_config.active.set(False)
                    await channel_config.last_trainer_id.set(message.author.id)
                    await channel_config.number.set(None)
                    await channel_config.start.set(None)
    
class ScanImage:

    def __init__(self, image):
        self.__image = Image.open(BytesIO(image))
        self.x, self.y = self.__image.size
        self.cp = self.__guess_number()
    
    def __get_tesseract(self):
        tools = pyocr.get_available_tools()
        
        if len(tools) == 0:
            print("No OCR tools found.")
            return None
        
        # TBH, IDK if tesseract is always [0]
        return tools[0]
    
    def __crop_percentage(self):
        # Might need adjusting
        return self.__image.crop((
            self.x * 0.3,
            self.y * 0.02,
            self.x * 0.7,
            self.y * 0.2
        ))
    
    def __guess_number(self):
        text = self.__get_tesseract().image_to_string(
            self.__crop_percentage(),
            lang="eng",
            builder=pyocr.builders.TextBuilder()
        )
        
        restructured_text = text.replace("l", "1").replace("o", "0").replace("I", "1").replace("O", "0")
        
        print(f"Found: {text}")
        if re.search('\d{2,4}', restructured_text):
            guess = int(re.search('\d{2,4}', restructured_text).group())
            print(f"Guess: {guess}")
            return guess
        return None
