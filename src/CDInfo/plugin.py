from codecs import getincrementaldecoder
from re import sub
from xml.dom.minidom import Element, parseString
from enigma import eConsoleAppContainer, eEnv
from Components.config import config, ConfigSubsection, ConfigInteger, ConfigYesNo, ConfigText
from Plugins.Plugin import PluginDescriptor
from Screens.Setup import Setup

config.plugins.CDInfo = ConfigSubsection()
config.plugins.CDInfo.useCDTEXT = ConfigYesNo(default=True)
config.plugins.CDInfo.useCDDB = ConfigYesNo(default=True)
config.plugins.CDInfo.displayString = ConfigText("$i - $t ($a)", fixed_size=False)
config.plugins.CDInfo.preferCDDB = ConfigYesNo(default=False)
config.plugins.CDInfo.CDDB_server = ConfigText("freedb.freedb.org", fixed_size=False)
config.plugins.CDInfo.CDDB_port = ConfigInteger(8880, limits=(1, 65536))
config.plugins.CDInfo.CDDB_timeout = ConfigInteger(20, limits=(-1, 60))
config.plugins.CDInfo.CDDB_cache = ConfigYesNo(default=True)

CDTEXTINFO = f'{eEnv.resolve("${bindir}")}/cdtextinfo'


class CDInfo(Setup):
	def __init__(self, session):
		Setup.__init__(self, session, "CDInfo", plugin="Extensions/CDInfo", PluginLanguageDomain="CDInfo")


class Query:
	def __init__(self, mediaplayer):
		self.playlist = mediaplayer.playlist
		self.mp = mediaplayer
		self.cddb_container = eConsoleAppContainer()
		self.cddb_output = ""
		self.cddb_decoder = getincrementaldecoder("utf-8")("replace")
		self.cdtext_container = eConsoleAppContainer()
		self.cdtext_output = ""
		self.cdtext_decoder = getincrementaldecoder("utf-8")("replace")
		self.tracklisting = {}
		self.albuminfo = {}

	def get_text(self, nodelist):
		rc = ""
		for node in nodelist:
			if node.nodeType == node.TEXT_NODE:
				rc += node.data
		return rc

	def xml_parse_output(self, string):
		data = string.decode("utf-8", "replace") if isinstance(string, bytes) else string
		data = sub(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9A-Fa-f]+);)", "&amp;", data)
		try:
			cdinfodom = parseString(data)
		except Exception:
			print("[xml_parse_output] error, could not parse")
			return False
		xmldata = cdinfodom.childNodes[0]
		queries = xmldata.childNodes
		self.xml_parse_query(queries)
		print(f"[xml_parse_output] albuminfo: {self.albuminfo}")
		print(f"[xml_parse_output] tracklisting: {self.tracklisting}")
		return True

	def xml_parse_query(self, queries_xml):
		for queries in queries_xml:
			if queries.nodeType == Element.nodeType:
				if queries.tagName == 'query':
					print(f"[xml_parse_query] cdinfo source is {queries.getAttribute('source')}, hit {queries.getAttribute('match')} of {queries.getAttribute('num_matches')}")
					for query in queries.childNodes:
						if query.nodeType == Element.nodeType:
							if query.tagName == 'albuminfo':
								self.xml_parse_albuminfo(query.childNodes)
							elif query.tagName == 'tracklisting':
								self.xml_parse_tracklisting(query.childNodes)

	def xml_parse_albuminfo(self, albuminfo_xml):
		for albuminfo in albuminfo_xml:
			if albuminfo.nodeType == Element.nodeType:
				if albuminfo.tagName == 'PERFORMER' or albuminfo.tagName == 'artist':
					artist = self.get_text(albuminfo.childNodes)
					self.albuminfo["artist"] = artist
				elif albuminfo.tagName.upper() == 'TITLE':
					title = self.get_text(albuminfo.childNodes)
					self.albuminfo["title"] = title
				elif albuminfo.tagName.upper() == 'YEAR':
					year = self.get_text(albuminfo.childNodes)
					self.albuminfo["year"] = year
				elif albuminfo.tagName.upper() == 'GENRE':
					genre = self.get_text(albuminfo.childNodes)
					self.albuminfo["genre"] = genre
				elif albuminfo.tagName == 'category' and "GENRE" not in self.albuminfo:
					category = self.get_text(albuminfo.childNodes)
					self.albuminfo["genre"] = category

	def xml_parse_tracklisting(self, tracklisting_xml):
		for tracklist in tracklisting_xml:
			if tracklist.nodeType == Element.nodeType:
				if tracklist.tagName == 'track':
					index = int(tracklist.getAttribute("number"))
					trackinfo = {}
					for track in tracklist.childNodes:
						if track.nodeType == Element.nodeType:
							if track.tagName == 'PERFORMER' or track.tagName == 'artist':
								artist = self.get_text(track.childNodes)
								trackinfo["artist"] = artist
							if track.tagName.upper() == 'TITLE':
								title = self.get_text(track.childNodes)
								trackinfo["title"] = title
							#elif track.tagName == 'length':
								#tracktext += "Dauer=%ss " % self.getText(track.childNodes)
							self.tracklisting[index] = trackinfo

	def update_albuminfo(self, replace=False):
		for tag in self.albuminfo:
			if tag not in self.mp.AudioCD_albuminfo or replace:
				self.mp.AudioCD_albuminfo[tag] = self.albuminfo[tag]

	def update_playlist(self, replace=False):
		for idx in range(len(self.playlist)):
			ref = self.playlist.getServiceRefList()[idx]
			track = idx + 1
			if idx < len(self.tracklisting) and (replace or not ref.getName()):
				trackinfo = self.tracklisting[track]
				display_string = config.plugins.CDInfo.displayString.value.replace("$i", str(track))
				if "title" in trackinfo:
					display_string = display_string.replace("$t", trackinfo["title"])
				if "artist" in trackinfo:
					display_string = display_string.replace("$a", trackinfo["artist"])
				ref.setName(display_string)
				self.playlist.updateFile(idx, ref)
		self.playlist.updateList()

	def scan(self):
		if config.plugins.CDInfo.useCDTEXT.value:
			self.cdtext_scan()
		if config.plugins.CDInfo.useCDDB.value:
			self.cddb_scan()

	def cdtext_scan(self):
		cmd = [CDTEXTINFO, CDTEXTINFO, "-xalT"]
		print(f"[cdtext_scan] {' '.join(cmd)}")
		self.cdtext_container.appClosed.append(self.cdtext_finished)
		self.cdtext_container.dataAvail.append(self.cdtext_avail)
		self.cdtext_container.execute(*cmd)

	def cddb_scan(self):
		cmd = [CDTEXTINFO, CDTEXTINFO, "-xalD", f"--cddb-port={config.plugins.CDInfo.CDDB_port.value}", f"--cddb-server={config.plugins.CDInfo.CDDB_server.value}", f"--cddb-timeout={config.plugins.CDInfo.CDDB_timeout.value}"]
		if not config.plugins.CDInfo.CDDB_cache.value:
			cmd += ["--no-cddb-cache"]
		print(f"[cddb_scan] {' '.join(cmd)}")
		self.cddb_container.appClosed.append(self.cddb_finished)
		self.cddb_container.dataAvail.append(self.cddb_avail)
		self.cddb_container.execute(*cmd)

	def cddb_avail(self, string):
		if isinstance(string, bytes):
			self.cddb_output += self.cddb_decoder.decode(string)
		else:
			self.cddb_output += string

	def cdtext_avail(self, string):
		if isinstance(string, bytes):
			self.cdtext_output += self.cdtext_decoder.decode(string)
		else:
			self.cdtext_output += string

	def cddb_finished(self, retval):
		self.cddb_container.appClosed.remove(self.cddb_finished)
		self.cddb_container.dataAvail.remove(self.cddb_avail)
		self.cddb_output += self.cddb_decoder.decode(b"", final=True)
		self.cddb_decoder.reset()
		if self.xml_parse_output(self.cddb_output):
			self.update_playlist(replace=config.plugins.CDInfo.preferCDDB.value)
			self.update_albuminfo(replace=config.plugins.CDInfo.preferCDDB.value)
			self.mp.readTitleInformation()
			self.cddb_output = ""

	def cdtext_finished(self, retval):
		self.cdtext_container.appClosed.remove(self.cdtext_finished)
		self.cdtext_container.dataAvail.remove(self.cdtext_avail)
		self.cdtext_output += self.cdtext_decoder.decode(b"", final=True)
		self.cdtext_decoder.reset()
		if self.xml_parse_output(self.cdtext_output):
			self.update_playlist(replace=not config.plugins.CDInfo.preferCDDB.value)
			self.update_albuminfo(replace=not config.plugins.CDInfo.preferCDDB.value)
			self.mp.readTitleInformation()
			self.cdtext_output = ""


def main(session, **kwargs):
	session.open(CDInfo)


def Plugins(**kwargs):
	return [PluginDescriptor(name="CDInfo", description=_("AudioCD info from CDDB & CD-Text"), where=PluginDescriptor.WHERE_PLUGINMENU, fnc=main, icon="plugin.png")]
