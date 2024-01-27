# -*- encoding: utf-8 -*-
import os

import websockets
import asyncio

import argparse
import json

import wave


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host",
                        type=str,
                        default="localhost",
                        required=False,
                        help="host ip, localhost, 127.0.0.1")
    parser.add_argument("--port",
                        type=int,
                        default=12395,
                        required=False,
                        help="grpc server port")
    parser.add_argument("--chunk_size",
                        type=str,
                        default="5, 10, 5",
                        help="chunk")
    parser.add_argument("--encoder_chunk_look_back",
                        type=int,
                        default=4,
                        help="chunk")
    parser.add_argument("--decoder_chunk_look_back",
                        type=int,
                        default=0,
                        help="chunk")
    parser.add_argument("--chunk_interval",
                        type=int,
                        default=10,
                        help="chunk")
    parser.add_argument("--hotword",
                        type=str,
                        default="",
                        help="hotword file path, one hotword perline (e.g.:阿里巴巴 20)")
    parser.add_argument("--audio_in",
                        type=str,
                        default=None,
                        help="audio_in")
    parser.add_argument("--audio_fs",
                        type=int,
                        default=16000,
                        help="audio_fs")
    parser.add_argument("--send_without_sleep",
                        action="store_true",
                        default=True,
                        help="if audio_in is set, send_without_sleep")
    parser.add_argument("--thread_num",
                        type=int,
                        default=1,
                        help="thread_num")
    parser.add_argument("--words_max_print",
                        type=int,
                        default=10000,
                        help="chunk")
    parser.add_argument("--output_dir",
                        type=str,
                        default=None,
                        help="output_dir")
    parser.add_argument("--ssl",
                        type=int,
                        default=0,
                        help="1 for ssl connect, 0 for no ssl")
    parser.add_argument("--use_itn",
                        type=int,
                        default=1,
                        help="1 for using itn, 0 for not itn")
    parser.add_argument("--mode",
                        type=str,
                        default="offline",
                        help="offline, online, 2pass")
    return parser


# offline_msg_done = False


async def record_from_scp(args, websocket, done_event):
    wavs = [args.audio_in]

    hotword_msg = ""

    wav_format = "pcm"
    use_itn = True
    if args.use_itn == 0:
        use_itn = False

    wav = wavs[0]
    wav_splits = wav.strip().split()

    wav_name = wav_splits[0] if len(wav_splits) > 1 else "demo"
    wav_path = wav_splits[1] if len(wav_splits) > 1 else wav_splits[0]
    if not len(wav_path.strip()) > 0:
        return

    with wave.open(wav_path, "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())
        audio_bytes = bytes(frames)

    stride = int(60 * args.chunk_size[1] / args.chunk_interval / 1000 * sample_rate * 2)
    chunk_num = (len(audio_bytes) - 1) // stride + 1

    # send first time
    message = json.dumps({"mode": args.mode,
                          "chunk_size": args.chunk_size,
                          "chunk_interval": args.chunk_interval,
                          "encoder_chunk_look_back": args.encoder_chunk_look_back,
                          "decoder_chunk_look_back": args.decoder_chunk_look_back,
                          "audio_fs": sample_rate,
                          "wav_name": wav_name,
                          "wav_format": wav_format,
                          "is_speaking": True,
                          "hotwords": hotword_msg,
                          "itn": use_itn})

    await websocket.send(message)

    for i in range(chunk_num):

        beg = i * stride
        data = audio_bytes[beg:beg + stride]
        message = data

        await websocket.send(message)
        if i == chunk_num - 1:
            is_speaking = False
            message = json.dumps({"is_speaking": is_speaking})

            await websocket.send(message)

        sleep_duration = 0.001
        await asyncio.sleep(sleep_duration)

    await asyncio.sleep(0.01)

    # global offline_msg_done
    # while not offline_msg_done:
    while not done_event.is_set():
        await asyncio.sleep(0.01)
    await websocket.close()


async def message(websocket, done_event):
    # global offline_msg_done
    text_print = ""
    pure_text = ""
    try:
        while True:
            meg = await websocket.recv()
            meg = json.loads(meg)

            text = meg["text"]
            timestamp = ""
            # offline_msg_done = meg.get("is_final", False)
            if meg.get("is_final", False):
                done_event.set()
            if "timestamp" in meg:
                timestamp = meg["timestamp"]
            pure_text += text
            if timestamp != "":
                text_print += "{} timestamp: {}".format(text, timestamp)
            else:
                text_print += "{}".format(text)

            # print("\r" + wav_name + ": " + text_print)
            # offline_msg_done = True
            done_event.set()
    except Exception as e:
        pass
        # print("Exception:", e)
    return pure_text


async def ws_client(wav_file):
    global offline_msg_done

    parser = get_parser()
    args = parser.parse_args(["--audio_in", wav_file])
    args.chunk_size = [int(x) for x in args.chunk_size.split(",")]
    if args.output_dir is not None:
        if not os.path.exists(args.output_dir):
            os.makedirs(args.output_dir)

    # offline_msg_done = False

    uri = "ws://{}:{}".format(args.host, args.port)
    ssl_context = None

    done_event = asyncio.Event()

    # print("connect to", uri)
    async with websockets.connect(uri, subprotocols=["binary"], ping_interval=None, ssl=ssl_context) as websocket:
        record_task = asyncio.create_task(record_from_scp(args, websocket, done_event))
        message_task = asyncio.create_task(message(websocket, done_event))
        await record_task  # 等待record_from_scp完成
        pure_text = await message_task  # 等待message完成并获取返回值
    return pure_text  # 返回message函数的返回值


def audio_trans(wav_file) -> str:
    return asyncio.run(ws_client(wav_file))


if __name__ == '__main__':
    wav_file = "/home/huangshiyu/mfs_v2/Task/audio/data/test_wav/baba.wav"
    text = audio_trans(wav_file)
    print("text:", text)
