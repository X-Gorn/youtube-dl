#coding:utf8
from __future__ import division, print_function, unicode_literals
import downloader
import ree as re
from utils import Soup, urljoin, LazyUrl, Downloader, try_n, join
import os
import json


@Downloader.register
class Downloader_nhentai(Downloader):
    type = 'nhentai'
    URLS = ['nhentai.net']
    MAX_CORE = 16
    
    def init(self):
        self.url = self.url.replace('nhentai_', '')
        self.url = 'https://nhentai.net/g/{}/'.format(self.id)

    @property
    def id(self):
        try:
            return int(self.url)
        except:
            return int(re.find('/g/([0-9]+)', self.url))

    def read(self):
        info, imgs = get_imgs(self.id)

        # 1225
        artist = join(info.artists)
        self.customWidget.artist = artist if info.artists else None
        group = join(info.groups) if info.groups else 'N／A'
        lang = info.lang if info.lang else 'N／A'
        series = info.seriess[0] if info.seriess else 'N／A'
        title = self.format_title(info.type, info.id, info.title, artist, group, series, lang)

        for img in imgs:
            self.urls.append(img.url)

        self.title = title


@LazyUrl.register
class LazyUrl_nhentai(LazyUrl):
    type = 'nhentai'
    def dump(self):
        referer = self._url
        url = self.image.url_img
        return {
            'referer': referer,
            'url': url,
            'p': self.image.p,
            }
    @classmethod
    def load(cls, data):
        referer = data['referer']
        url = data['url']
        img = Image(referer, url, data['p'])
        return img.url
        
    
class Image(object):
    def __init__(self, url_page, url_img, p):
        self.p = p
        self.referer = url_page
        self.filename = os.path.basename(url_img)
        self.url_img = url_img
        def f(_):
            return self.url_img
        self.url = LazyUrl_nhentai(url_page, f, self)


class Info(object):
    def __init__(self, host, id, id_media, title, p, artists, groups, seriess, lang, type, formats):
        self.host = host
        self.id = id
        self.id_media = id_media
        self.title = title
        self.p = p
        self.artists = artists
        self.groups = groups
        self.seriess = seriess
        self.lang = lang
        self.type = type
        self.formats = formats


@try_n(4)
def get_info(id):
    url = 'https://nhentai.net/g/{}/1/'.format(id)
    referer = 'https://nhentai.net/g/{}/'.format(id)
    html = downloader.read_html(url, referer=referer)

    data = html.split('JSON.parse(')[1].split(');')[0]
    gal = json.loads(json.loads(data))
    host = re.find('''media_url: *['"]([^'"]+)''', html)
    if not host:
        raise Exception('no host')
    
    id = int(gal['id'])
    id_media = int(gal['media_id'])
    title = gal['title']['english']
    p = len(gal['images']['pages'])
    artists = []
    groups = []
    seriess = []
    for tag in gal['tags']:
        type = tag['type']
        if type == 'artist':
            artists.append(tag['name'])
        elif type == 'group':
            groups.append(tag['name'])
        elif type == 'parody' and tag['name'] != 'original':
            seriess.append(tag['name'])
        elif type == 'language':
            lang = tag['name']
        elif type == 'category':
            type_ = tag['name']
    formats = []
    for img in gal['images']['pages']:
        type = img['t']
        format = {'j':'jpg', 'p':'png', 'g':'gif'}[type]
        formats.append(format)
    info = Info(host, id, id_media, title, p, artists, groups, seriess, lang, type_, formats)
    return info


def get_imgs(id):
    info = get_info(id)

    imgs = []
    for p in range(1, info.p+1):
        name = '/galleries/{}/{}.{}'.format(info.id_media, p, info.formats[p-1])
        url_page = 'https://nhentai.net/g/{}/{}/'.format(id, p)
        url_img = urljoin(info.host, name)
        img = Image(url_page, url_img, p)
        imgs.append(img)

    return info, imgs


