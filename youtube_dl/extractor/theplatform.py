from __future__ import unicode_literals

import re
import json
import time
import hmac
import binascii
import hashlib


from .common import InfoExtractor
from ..utils import (
    determine_ext,
    ExtractorError,
    xpath_with_ns,
    unsmuggle_url,
    int_or_none,
    url_basename,
    float_or_none,
)

default_ns = 'http://www.w3.org/2005/SMIL21/Language'
_x = lambda p: xpath_with_ns(p, {'smil': default_ns})


class ThePlatformBaseIE(InfoExtractor):
    def _extract_theplatform_smil_formats(self, smil_url, video_id, note='Downloading SMIL data'):
        meta = self._download_xml(smil_url, video_id, note=note)
        try:
            error_msg = next(
                n.attrib['abstract']
                for n in meta.findall(_x('.//smil:ref'))
                if n.attrib.get('title') == 'Geographic Restriction' or n.attrib.get('title') == 'Expired')
        except StopIteration:
            pass
        else:
            raise ExtractorError(error_msg, expected=True)

        formats = self._parse_smil_formats(
            meta, smil_url, video_id, namespace=default_ns,
            # the parameters are from syfy.com, other sites may use others,
            # they also work for nbc.com
            f4m_params={'g': 'UXWGVKRWHFSP', 'hdcore': '3.0.3'},
            transform_rtmp_url=lambda streamer, src: (streamer, 'mp4:' + src))

        for _format in formats:
            ext = determine_ext(_format['url'])
            if ext == 'once':
                _format['ext'] = 'mp4'

        self._sort_formats(formats)

        return formats

    def get_metadata(self, path, video_id):
        info_url = 'http://link.theplatform.com/s/%s?format=preview' % path
        info_json = self._download_webpage(info_url, video_id)
        info = json.loads(info_json)

        subtitles = {}
        captions = info.get('captions')
        if isinstance(captions, list):
            for caption in captions:
                lang, src, mime = caption.get('lang', 'en'), caption.get('src'), caption.get('type')
                subtitles[lang] = [{
                    'ext': 'srt' if mime == 'text/srt' else 'ttml',
                    'url': src,
                }]

        return {
            'title': info['title'],
            'subtitles': subtitles,
            'description': info['description'],
            'thumbnail': info['defaultThumbnailUrl'],
            'duration': int_or_none(info.get('duration'), 1000),
        }


class ThePlatformIE(ThePlatformBaseIE):
    _VALID_URL = r'''(?x)
        (?:https?://(?:link|player)\.theplatform\.com/[sp]/(?P<provider_id>[^/]+)/
           (?:(?P<media>(?:[^/]+/)+select/media/)|(?P<config>(?:[^/\?]+/(?:swf|config)|onsite)/select/))?
         |theplatform:)(?P<id>[^/\?&]+)'''

    _TESTS = [{
        # from http://www.metacafe.com/watch/cb-e9I_cZgTgIPd/blackberrys_big_bold_z30/
        'url': 'http://link.theplatform.com/s/dJ5BDC/e9I_cZgTgIPd/meta.smil?format=smil&Tracking=true&mbr=true',
        'info_dict': {
            'id': 'e9I_cZgTgIPd',
            'ext': 'flv',
            'title': 'Blackberry\'s big, bold Z30',
            'description': 'The Z30 is Blackberry\'s biggest, baddest mobile messaging device yet.',
            'duration': 247,
        },
        'params': {
            # rtmp download
            'skip_download': True,
        },
    }, {
        # from http://www.cnet.com/videos/tesla-model-s-a-second-step-towards-a-cleaner-motoring-future/
        'url': 'http://link.theplatform.com/s/kYEXFC/22d_qsQ6MIRT',
        'info_dict': {
            'id': '22d_qsQ6MIRT',
            'ext': 'flv',
            'description': 'md5:ac330c9258c04f9d7512cf26b9595409',
            'title': 'Tesla Model S: A second step towards a cleaner motoring future',
        },
        'params': {
            # rtmp download
            'skip_download': True,
        }
    }, {
        'url': 'https://player.theplatform.com/p/D6x-PC/pulse_preview/embed/select/media/yMBg9E8KFxZD',
        'info_dict': {
            'id': 'yMBg9E8KFxZD',
            'ext': 'mp4',
            'description': 'md5:644ad9188d655b742f942bf2e06b002d',
            'title': 'HIGHLIGHTS: USA bag first ever series Cup win',
        }
    }, {
        'url': 'http://player.theplatform.com/p/NnzsPC/widget/select/media/4Y0TlYUr_ZT7',
        'only_matching': True,
    }]

    @staticmethod
    def _sign_url(url, sig_key, sig_secret, life=600, include_qs=False):
        flags = '10' if include_qs else '00'
        expiration_date = '%x' % (int(time.time()) + life)

        def str_to_hex(str):
            return binascii.b2a_hex(str.encode('ascii')).decode('ascii')

        def hex_to_str(hex):
            return binascii.a2b_hex(hex)

        relative_path = url.split('http://link.theplatform.com/s/')[1].split('?')[0]
        clear_text = hex_to_str(flags + expiration_date + str_to_hex(relative_path))
        checksum = hmac.new(sig_key.encode('ascii'), clear_text, hashlib.sha1).hexdigest()
        sig = flags + expiration_date + checksum + str_to_hex(sig_secret)
        return '%s&sig=%s' % (url, sig)

    def _real_extract(self, url):
        url, smuggled_data = unsmuggle_url(url, {})

        mobj = re.match(self._VALID_URL, url)
        provider_id = mobj.group('provider_id')
        video_id = mobj.group('id')

        if not provider_id:
            provider_id = 'dJ5BDC'

        path = provider_id
        if mobj.group('media'):
            path += '/media'
        path += '/' + video_id

        if smuggled_data.get('force_smil_url', False):
            smil_url = url
        elif mobj.group('config'):
            config_url = url + '&form=json'
            config_url = config_url.replace('swf/', 'config/')
            config_url = config_url.replace('onsite/', 'onsite/config/')
            config = self._download_json(config_url, video_id, 'Downloading config')
            if 'releaseUrl' in config:
                release_url = config['releaseUrl']
            else:
                release_url = 'http://link.theplatform.com/s/%s?mbr=true' % path
            smil_url = release_url + '&format=SMIL&formats=MPEG4&manifest=f4m'
        else:
            smil_url = 'http://link.theplatform.com/s/%s/meta.smil?format=smil&mbr=true' % path

        sig = smuggled_data.get('sig')
        if sig:
            smil_url = self._sign_url(smil_url, sig['key'], sig['secret'])

        formats = self._extract_theplatform_smil_formats(smil_url, video_id)

        ret = self.get_metadata(path, video_id)
        ret.update({
            'id': video_id,
            'formats': formats,
        })

        return ret


class ThePlatformFeedIE(ThePlatformBaseIE):
    _URL_TEMPLATE = '%s//feed.theplatform.com/f/%s/%s?form=json&byGuid=%s'
    _VALID_URL = r'https?://feed\.theplatform\.com/f/(?P<provider_id>[^/]+)/(?P<feed_id>[^?/]+)\?(?:[^&]+&)*byGuid=(?P<id>[a-zA-Z0-9_]+)'
    _TEST = {
        # From http://player.theplatform.com/p/7wvmTC/MSNBCEmbeddedOffSite?guid=n_hardball_5biden_140207
        'url': 'http://feed.theplatform.com/f/7wvmTC/msnbc_video-p-test?form=json&pretty=true&range=-40&byGuid=n_hardball_5biden_140207',
        'md5': '22d2b84f058d3586efcd99e57d59d314',
        'info_dict': {
            'id': 'n_hardball_5biden_140207',
            'ext': 'mp4',
            'title': 'The Biden factor: will Joe run in 2016?',
            'description': 'Could Vice President Joe Biden be preparing a 2016 campaign? Mark Halperin and Sam Stein weigh in.',
            'thumbnail': 're:^https?://.*\.jpg$',
            'upload_date': '20140208',
            'timestamp': 1391824260,
            'duration': 467.0,
            'categories': ['MSNBC/Issues/Democrats', 'MSNBC/Issues/Elections/Election 2016'],
        },
    }

    def _real_extract(self, url):
        mobj = re.match(self._VALID_URL, url)

        video_id = mobj.group('id')
        provider_id = mobj.group('provider_id')
        feed_id = mobj.group('feed_id')

        real_url = self._URL_TEMPLATE % (self.http_scheme(), provider_id, feed_id, video_id)
        feed = self._download_json(real_url, video_id)
        entry = feed['entries'][0]

        formats = []
        first_video_id = None
        duration = None
        for item in entry['media$content']:
            smil_url = item['plfile$url'] + '&format=SMIL&Tracking=true&Embedded=true&formats=MPEG4,F4M'
            cur_video_id = url_basename(smil_url)
            if first_video_id is None:
                first_video_id = cur_video_id
                duration = float_or_none(item.get('plfile$duration'))
            formats.extend(self._extract_theplatform_smil_formats(smil_url, video_id, 'Downloading SMIL data for %s' % cur_video_id))

        self._sort_formats(formats)

        thumbnails = [{
            'url': thumbnail['plfile$url'],
            'width': int_or_none(thumbnail.get('plfile$width')),
            'height': int_or_none(thumbnail.get('plfile$height')),
        } for thumbnail in entry.get('media$thumbnails', [])]

        timestamp = int_or_none(entry.get('media$availableDate'), scale=1000)
        categories = [item['media$name'] for item in entry.get('media$categories', [])]

        ret = self.get_metadata('%s/%s' % (provider_id, first_video_id), video_id)
        ret.update({
            'id': video_id,
            'formats': formats,
            'thumbnails': thumbnails,
            'duration': duration,
            'timestamp': timestamp,
            'categories': categories,
        })

        return ret
