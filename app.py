#!/usr/bin/env python3
import sys
import gi
import logging

gi.require_version('GLib', '2.0')
gi.require_version('GObject', '2.0')
gi.require_version('Gst', '1.0')

from gi.repository import Gst, GObject, GLib

def start_pipeline():
    global seek_done
    seek_done = False
    print("Starting GStreamer pipeline...")
    # Initialize GStreamer
    logging.basicConfig(level=logging.DEBUG, format="[%(name)s] %(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)

    pipeline = None
    bus = None
    message = None
    data = None
    playing = False
    is_live = False
    seek_enabled = False
    seek_done = False

    # handler for pad_added signal
    # pad_added signal is triggered when a new pad is created on the source element (uridecodebin in this case)
    def pad_added_handler(src, new_pad, data):
        video_queue_element, audio_queue_element = data
        logger.debug(f"Received new pad: {new_pad.get_name()} from {src.get_name()}")

        #check new pad's capabilities
        new_pad_caps = new_pad.get_current_caps()  # query the capabilities of the new pad
        if not new_pad_caps:
            new_pad_caps = new_pad.query_caps(None)  # if no current caps, query the capabilities
        new_pad_structure = new_pad_caps.get_structure(0)  # get the first structure from the capabilities
        new_pad_type = new_pad_structure.get_name()  # get the name of the type of the new pad

        if new_pad_type.startswith("video/"):
            sink_pad = video_queue_element.get_static_pad("sink")  # get the sink pad of the convert element
            link_result = new_pad.link(sink_pad)
            logger.debug(f"linking new pad {new_pad.get_name()} of type {new_pad_type} ")
            #attempt to link the new pad to the convert element's sink pad
            if link_result != Gst.PadLinkReturn.OK:
                logger.error(f"Type of new pad {new_pad.get_name()} is not compatible with convert sink pad {sink_pad.get_name()}.")
            else:
                logger.debug(f"Pad {new_pad.get_name()} linked to convert sink pad {sink_pad.get_name()} successfully.")
        elif new_pad_type.startswith("audio/"):
            sink_pad = audio_queue_element.get_static_pad("sink")
            link_result = new_pad.link(sink_pad)
            logger.debug(f"linking new pad {new_pad.get_name()} of type {new_pad_type} ")
            #attempt to link the new pad to the convert element's sink pad
            if link_result != Gst.PadLinkReturn.OK:
                logger.error(f"Type of new pad {new_pad.get_name()} is not compatible with convert sink pad {sink_pad.get_name()}.")
            else:
                logger.debug(f"Pad {new_pad.get_name()} linked to convert sink pad {sink_pad.get_name()} successfully.")
        else:
            logger.error(f"Pad {new_pad.get_name()} has type {new_pad_type}, which is not compatible with the convert element's sink pad.")
            return

    
    #handler for message processesing
    def message_handler(pipeline, playing, msg):
        global seek_enabled
        if msg.type == Gst.MessageType.ERROR:
            err, debug_info = msg.parse_error()
            logger.error(f"Error received from element {msg.src.get_name()}: {err.message}")
            logger.error(f"Debugging information: {debug_info if debug_info else 'none'}")
        elif msg.type == Gst.MessageType.EOS:
            logger.info("End-Of-Stream reached. Stopping playback.")  
            #listening for buffering messages
        elif msg.type == Gst.MessageType.BUFFERING:
            percent = msg.parse_buffering()
            logger.info(f"new Buffering {percent}%")
            #if the stream is live, we don't care about buffering
            if is_live:
                logger.info("Stream is live, ignoring buffering message.")
                return
            # wait until buffering is 100% before start/resume playing
            if percent < 100:
                Gst.Element.set_state(pipeline, Gst.State.PAUSED)
                logger.info("Pipeline paused due to buffering.")
            else:
                Gst.Element.set_state(pipeline, Gst.State.PLAYING)
                logger.info("Pipeline resumed playing after buffering.")
            #listening for lost clock messages
        elif msg.type == Gst.MessageType.NEW_CLOCK:
            #get a new clock
            Gst.Element.set_state(pipeline, Gst.State.PAUSED)
            logger.warning("Lost clock message received. Pausing pipeline to reset clock.")
            Gst.Element.set_state(pipeline, Gst.State.PLAYING)
            logger
        elif msg.type == Gst.MessageType.DURATION_CHANGED:
            #the duration of the pipeline has changed mark the current duration as invalid
            duration = Gst.CLOCK_TIME_NONE
        elif msg.type == Gst.MessageType.STATE_CHANGED:
            
                old_state, new_state, pending_state = msg.parse_state_changed()
                logger.info(f"Pipeline state changed from {old_state.value_nick} to {new_state.value_nick} (pending: {pending_state.value_nick})")
        
                #remember if we are in playing state or not
                playing = (new_state == Gst.State.PLAYING)
                if playing:
                    logger.info("Pipeline is now in PLAYING state.")
                    # Check if seeking is enabled
                    seek_query = Gst.Query.new_seeking(Gst.Format.TIME)
                    seek_enabled = pipeline.query(seek_query)
                    logger.info(f"Seek enabled: {seek_enabled}")
                    # Call seek here, only once
                    if seek_enabled and not seek_done:
                        seek(pipeline, 10)  # Seek to 10 seconds, for example
                else:
                    logger.info(f"Pipeline is in {new_state.value_nick} not in PLAYING state anymore.")
                if new_state == Gst.State.PLAYING:
                    #when the pipeline is in playing state we can query the duration
                    duration = msg.src.query_duration(Gst.Format.TIME)[1]
                    if duration != Gst.CLOCK_TIME_NONE:
                        logger.info(f"Duration of the pipeline is {duration / Gst.SECOND} seconds.")
                    else:
                        logger.warning("Duration is not available.")
        elif msg.type == Gst.MessageType.BUFFERING:
            percent = msg.parse_buffering()
            logger.debug(f"new Buffering {percent}%")
            # Optionally, you can pause/resume pipeline based on buffering percent here
        elif msg.type == Gst.MessageType.QOS:
            logger.debug("QoS message received.")
                    
        else:
            logger.error(f"Unexpected message received: {msg.type}")

    # function to print the current position of the pipeline
    # this function will be called every second to print the current position of the pipeline
    def print_position(pipeline):
        success, position = pipeline.query_position(Gst.Format.TIME)
        if success and position != Gst.CLOCK_TIME_NONE:
            logger.info(f"Current position: {position / Gst.SECOND} seconds.")
        return True  # Continue calling this function

    def on_message(bus, message, loop, pipeline, playing):
        message_handler(pipeline, playing, message)
        if message.type == Gst.MessageType.ERROR or message.type == Gst.MessageType.EOS:
            logger.info("End of stream reached. Stopping playback.")
            loop.quit()
    #if seeking is enabled, we can seek to a specific position in the pipeline
    def seek(pipeline, position):
        global seek_enabled, seek_done
        if not seek_enabled:
            logger.warning("Seeking is not enabled.")
            return
        if seek_done:
            logger.warning("Seek operation already done.")
            return
        success = pipeline.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, position * Gst.SECOND)
        if success:
            logger.info(f"Seeked to {position} seconds.")
            seek_done = True
        else:
            logger.error("Seek failed.")

    def main():

        # initialize GStreamer
        #checks what plugins are available
        #Executes any commandline arguments intended for GStreamer
        Gst.init(sys.argv[1:])

        
        #create the elements
        #uridecodebin will internally instantiate all the necessary elements 
        # (sources, demuxers and decoders) to turn a URI into raw audio and/or video streams.
        source = Gst.ElementFactory.make("uridecodebin", "source") #the second parameter is the name we want to give to this particular instance
        video_convert = Gst.ElementFactory.make("videoconvert", "video_convert")
        audio_convert = Gst.ElementFactory.make("audioconvert", "audio_convert")
        resample = Gst.ElementFactory.make("audioresample", "resample")
        #video_sink = Gst.ElementFactory.make("autovideosink", "video_sink")
        #audio_sink = Gst.ElementFactory.make("autoaudiosink", "audio_sink")
        video_encoder = Gst.ElementFactory.make("vp8enc", "video_encoder")
        audio_encoder = Gst.ElementFactory.make("vorbisenc", "audio_encoder")
        webm_mux = Gst.ElementFactory.make("webmmux", "webm_mux")
        tcp_sink = Gst.ElementFactory.make("tcpserversink", "tcp_sink")
        video_queue = Gst.ElementFactory.make("queue", "video_queue")
        audio_queue = Gst.ElementFactory.make("queue", "audio_queue")

        # Set tcpserversink properties

        tcp_sink.set_property("host", "127.0.0.1")
        tcp_sink.set_property("port", 6000)

        webm_mux.set_property("streamable", True)



        # create empty pipeline
        pipeline = Gst.Pipeline.new("test-pipeline")

        if not pipeline or not source or not webm_mux or not tcp_sink or not video_convert or not resample or not audio_convert :
            logger.error("Not all elements could be created.")
            sys.exit(1)

        # build the pipeline
        # note: we are not linking the source at this point.
        pipeline.add(source)
        pipeline.add(video_queue)
        pipeline.add(video_convert)
        pipeline.add(video_encoder)
        pipeline.add(audio_queue)
        pipeline.add(audio_convert)
        pipeline.add(resample)
        pipeline.add(audio_encoder)
        pipeline.add(webm_mux)
        pipeline.add(tcp_sink)
        # Link the elements sequentially
        if not video_queue.link(video_convert):
            logger.error("Failed to link video queue to convert.")          
            sys.exit(1)
        if not video_convert.link(video_encoder):
            logger.error("Failed to link video convert to encoder.")
            sys.exit(1)
        if not video_encoder.link(webm_mux):
            logger.error("Failed to link video encoder to webm_mux.")
            sys.exit(1)
        if not audio_queue.link(audio_convert):
            logger.error("Failed to link audio queue to convert.")
            sys.exit(1)
        if not audio_convert.link(resample):
            logger.error("Failed to link audio convert to resample.")
            sys.exit(1)
        if not resample.link(audio_encoder):
            logger.error("failed to link resample to audio encoder.")
            sys.exit(1)
        if not audio_encoder.link(webm_mux):
            logger.error("Failed to link audio encoder to webm_mux.")
            sys.exit(1)
        if not webm_mux.link(tcp_sink):
            logger.error("Failed to link webm_mux to tcp_sink.")
            sys.exit(1)
        # modify the source properties if needed
        #source.set_property("pattern", 18)  # 0 is the default pattern for videotestsrc

        # set the URI of the file to play
        source.set_property("uri", "https://gstreamer.freedesktop.org/data/media/sintel_trailer-480p.webm")  

        #connect the "pad-added" signal to our source uridecodebin element
        source.connect("pad-added", pad_added_handler, (video_queue, audio_queue))#convert is the element we want to link to the newly created pad from the source element.


        # start playing
        ret = pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            logger.error("Unable to set the pipeline to the playing state.")
            sys.exit(1)
        elif ret == Gst.StateChangeReturn.NO_PREROLL:
            is_live = True
            logger.info("Pipeline is live, no prerolling required.")
            return is_live
        # wait until EOS or error
        bus = pipeline.get_bus() #retrieve the pipeline's bus

        #if no message is received within one thenth of a second, the function will return None
        # we are interested in messages of type ERROR, EOS, STATE_CHANGED and DURATION_CHANGED

    # Create a GLib MainLoop
        loop = GLib.MainLoop()

        # Add the print_position timer
        #GLib.timeout_add_seconds(1, print_position, pipeline)

        # Add bus watch to handle messages asynchronously
        bus.add_signal_watch()
        bus.connect("message", on_message, loop, pipeline, playing)

        # Run the main loop (this will process both bus messages and timeouts)
        try:
            loop.run()
        except KeyboardInterrupt:
            logger.info("Interrupted by user, stopping...")
        finally:
            pipeline.set_state(Gst.State.NULL)

    main()