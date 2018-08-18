from .cpgame import CPGame
import pyocr

def setup(bot):
    if bool(pyocr.get_available_tools()):
        bot.add_cog(CPGame(bot))
    else:
        print("No OCR tools found.")
