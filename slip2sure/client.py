import aiohttp
import uuid
from aiohttp import FormData
from io import BytesIO
from uuid import uuid4

from .exception import Slip2SureError
from .model import Slip2SureTruemoney, Slip2SureBankSlip

class Slip2SureAPI:
    __API_URL = "https://api.slip2sure.com/api/v0"
    __API_KEY = None

    __FILE_EXT = {
        "89504e": { "ext": "png", "mime": "image/png" },
        "ffd8ff": { "ext": "jpg", "mime": "image/jpg" },
    }

    def __init__(self, api_key: str):
        self.__API_KEY = api_key
    
    async def scanTruemoneySlip(self, file: bytes):
        # UUID
        uid = str(uuid.uuid4())
        # Get extension
        ext = self.__FILE_EXT.get(file[0:3].hex(), None)
        if ext is None:
            raise Exception("Please upload image.")

        # Create form data
        form = FormData()
        form.add_field('image', BytesIO(file), filename=f"{str(uuid4())}.{ext["ext"]}", content_type=ext["mime"])

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.__API_URL}/truemoney/v1/verify", headers=self.__getHeaders(), data=form) as response:
                # Parse to JSON
                js = await response.json()
                # Check if success or not
                if response.status != 200:
                    raise Slip2SureError(js["result"], js["message"])

                return Slip2SureTruemoney(**js)

    async def scanBankSlipByPayload(self, payload: str):
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.__API_URL}/bank/v0/verifyByPayload", headers=self.__getHeaders(), json={"payload": payload}) as response:
                # Parse to JSON
                js = await response.json()
                # Check if success or not
                if response.status != 200:
                    raise Slip2SureError(js["result"], js["message"])
                    
                
                print(js)
                return Slip2SureBankSlip(**js)

    def __getHeaders(self):
        return {
            "x-api-key": self.__API_KEY
        }