import json
import time
import websocket
import threading
import logging

class WebsocketClient():
    def __init__(self, urls, topics, block_queue, tx_queue):
        self.urls = urls
        self.topics = topics
        self.ws = None
        self.block_queue = block_queue
        self.tx_queue = tx_queue
        self.NewBlock = False
        
        self.logger = logging.getLogger("Websocket")
        self.logger.setLevel(logging.INFO)
    
    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            self.NewBlock = True
            if "result" in data and "query" in data["result"]:
                if data["result"]["query"] == "tm.event='NewBlock'" or data["result"]["query"] == "tm.event='ValidatorSetUpdates'":
                    self.block_queue.put(data)
                elif data["result"]["query"] == "tm.event='Tx' AND message.action CONTAINS 'MsgSubmitProposal'":
                    self.tx_queue.put(data)
        except Exception as e:
            self.logger.error(f"Error parsing message: {e}")

    def on_error(self, ws, error):
        self.logger.error(f"Error: {error}")
        
    def on_close(self, ws, close_status_code, close_msg):
        self.logger.error(f"Connection closed with status code: {close_status_code}, message: {close_msg}")
        
    def on_open(self, ws):
        for topic in self.topics:
            self.ws.send(json.dumps(topic))
        self.logger.info("Subscribed to get info")
    
    # def check_uptime(self):
    #     while True:
    #         time.sleep(600)
    #         if not self.ws.sock or not self.ws.sock.connected:
    #             self.logger.error("WebSocket connection is not active")
    #             continue
            
    #         if not self.NewBlock:
    #             self.logger.error("No new data in 20 minutes")
    #             self.ws.close()
    #             return
    #         else:
    #             self.NewBlock = False
        
    def _send_ping(self):
        """ Send a ping to the server periodically to keep the connection alive """
        while self.ws and self.ws.sock and self.ws.sock.connected:
            time.sleep(30)  # Ping every 30 seconds (you can adjust this based on the server)
            self.ws.send("ping")  # Send a ping message, if required by the server

    def connect(self):
        while True:
            for url in self.urls:
                try:
                    self.logger.info(f"Connecting to {url}...")
                    self.ws = websocket.WebSocketApp(
                        url,
                        on_open=self.on_open,
                        on_message=self.on_message,
                        on_error=self.on_error,
                        on_close=self.on_close
                    )
                    timeout_thread = threading.Thread(target=self._send_ping)
                    timeout_thread.daemon = True
                    timeout_thread.start()
                    self.ws.run_forever(ping_interval=60, ping_timeout=30)
                except Exception as e:
                    self.logger.error(f"Error connecting to {url}: {e}")
                    time.sleep(10)
                else:
                    self.logger.error(f"Connection lost with {url}. Retrying next url...")
                    time.sleep(10)
        