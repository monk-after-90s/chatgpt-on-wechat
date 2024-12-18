import sys
import asyncio

async def read_stream(stream, callback):
    while True:
        line = await stream.readline()
        if not line:
            break
        callback(line.decode().strip())

async def run_command():
    process = await asyncio.create_subprocess_exec(
        sys.executable, 'app.py',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={'PYTHONUNBUFFERED': '1'}
    )


    await asyncio.gather(
        read_stream(process.stdout, lambda line: print(f"STDOUT: {line}")),
        read_stream(process.stderr, lambda line: print(f"STDERR: {line}"))
    )

    return await process.wait()

if __name__ == '__main__':
    asyncio.run(run_command())