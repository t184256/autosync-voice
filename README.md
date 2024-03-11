# autosync-voice

I sometimes record audio simultaneously on two voice recorders at once.
Then I just wanna plug them into my PC
and get the recordings automatically synchronized and combined
into a single stereo track.

This is a set of to automatically:

1. import recordings from my devices and transcode them into FLAC for archival
2. find pairs of recordings starting at the approximately same time
3. combine the two into a single recording
4. de-noise the combined recording (DeepFilterNet)
5. transcode the result into Opus
