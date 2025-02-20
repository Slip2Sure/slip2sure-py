# Slip2Sure Python
SDK สำหรับเชื่อมต่อกับระบบ [Slip2Sure](https://slip2sure.com) Service. (Python)

หากต้องการอ่าน API Document สามารถอ่านได้ที่ [API Document](https://app.slip2sure.com/user/api/docs)

## Install
```sh
pip install git+https://github.com/Slip2Sure/slip2sure-py
```

## Usage
```py
import asyncio
from slip2sure import Slip2SureAPI

async def main():
    client = Slip2SureAPI("YOUR_API_KEY")

    # You can use Flask, FastAPI for recieve body
    with open("FILE_PATH", "rb") as f: 
        result = await client.scanTruemoneySlip(f.read())
        print(result)

asyncio.run(main())
```

## LICENSE
[MIT](./LICENSE)