import json
import httpx
import pytest
from igallery.config import load_settings
from igallery.immich import ImmichClient, SourceError

ID = '00000000-0000-0000-0000-000000000001'
CFG = load_settings({'IMMICH_URL': 'https://nas.example', 'IMMICH_API_KEY': 'unit-test-secret'})

async def test_random_filters_duplicates_and_videos():
    def handler(req):
        assert req.url.path == '/api/search/random'
        assert json.loads(req.content) == {'size': 100, 'withExif': True, 'filter': {'type': {'eq': 'IMAGE'}, 'visibility': {'notIn': ['locked']}}}
        assert req.headers['x-api-key'] == 'unit-test-secret'
        return httpx.Response(200, json=[{'id': ID, 'type': 'IMAGE', 'visibility': 'timeline'}, {'id': ID, 'type': 'IMAGE', 'visibility': 'timeline'}, {'id': '../bad', 'type': 'IMAGE', 'visibility': 'timeline'}, {'id': '00000000-0000-0000-0000-000000000002', 'type': 'VIDEO'}])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert await ImmichClient(CFG, http).list_photos() == [{'id': ID, 'taken_date': None, 'location': None}]

async def test_album():
    cfg = load_settings({'IMMICH_URL': 'https://nas.example', 'IMMICH_API_KEY': 'unit-test-secret', 'IMMICH_ALBUM_ID': ID, 'IGALLERY_CACHE_COUNT': '1'})
    def handler(req):
        assert req.url.path == '/api/albums/' + ID
        return httpx.Response(200, json={'assets': [{'id': ID, 'type': 'IMAGE', 'visibility': 'timeline'}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert await ImmichClient(cfg, http).list_photos() == [{'id': ID, 'taken_date': None, 'location': None}]

async def test_thumbnail():
    def handler(req):
        assert req.url.path == '/api/assets/' + ID + '/thumbnail'
        assert req.url.params['size'] == 'preview'
        return httpx.Response(200, content=b'jpeg', headers={'content-type': 'image/jpeg'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert await ImmichClient(CFG, http).download(ID) == b'jpeg'

@pytest.mark.parametrize('response', [httpx.Response(401), httpx.Response(500), httpx.Response(302, headers={'location': 'https://evil.example'}), httpx.Response(200, json={}), httpx.Response(200, content=b'bad')])
async def test_source_errors_are_safe(response):
    requests = []
    def handler(req):
        requests.append(req)
        return response
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as http:
        with pytest.raises(SourceError) as error:
            await ImmichClient(CFG, http).list_photos()
        assert 'unit-test-secret' not in str(error.value)
        assert len(requests) == 1

async def test_timeout_and_invalid_id():
    def handler(req):
        raise httpx.ReadTimeout('unit-test-secret', request=req)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ImmichClient(CFG, http)
        for action in (client.list_photos(), client.download('../bad'), client.download(ID)):
            with pytest.raises(SourceError) as error:
                await action
            assert 'unit-test-secret' not in str(error.value)

@pytest.mark.parametrize('content,headers', [(b'<html>', {'content-type': 'text/html'}), (b'a', {'content-type': 'image/jpeg', 'content-length': str(26*1024*1024)})])
async def test_rejects_nonimage_or_oversize(content, headers):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=content, headers=headers))) as http:
        with pytest.raises(SourceError):
            await ImmichClient(CFG, http).download(ID)

async def test_invalid_transport_url_is_sanitized():
    def handler(req):
        raise httpx.InvalidURL('unit-test-secret')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(SourceError) as error:
            await ImmichClient(CFG, http).list_photos()
        assert 'unit-test-secret' not in str(error.value)

@pytest.mark.parametrize('metadata,expected', [
    ({'localDateTime': '2020-01-02T00:30:00', 'exifInfo': {'dateTimeOriginal': '2020-01-01T16:30:00Z'}}, '2020-01-02'),
    ({'exifInfo': {'dateTimeOriginal': '2020-01-02T00:30:00+08:00'}}, '2020-01-02'),
    ({'createdAt': '2026-10-07T00:00:00Z', 'fileCreatedAt': '2026-10-07T00:00:00Z'}, None),
    ({'localDateTime': '2020-02-30T00:00:00', 'exifInfo': None}, None),
    ({'localDateTime': '2020-01-02-not-a-timestamp', 'exifInfo': None}, None),
])
async def test_photo_dates_preserve_local_day_and_never_use_upload_time(metadata, expected):
    asset = {'id': ID, 'type': 'IMAGE', 'visibility': 'timeline', **metadata}
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=[asset]))) as http:
        assert await ImmichClient(CFG, http).list_photos() == [{'id': ID, 'taken_date': expected, 'location': None}]

@pytest.mark.parametrize('visibility', ['locked', None, 'unknown', {'unexpected': 'locked'}])
async def test_untrusted_visibility_is_not_returned(visibility):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=[
        {'id': ID, 'type': 'IMAGE', 'visibility': visibility}
    ]))) as http:
        assert await ImmichClient(CFG, http).list_photos() == []

@pytest.mark.parametrize('exif,expected', [
    ({'country': 'China', 'state': 'Guangxi', 'city': 'Nanning'}, 'China / Guangxi / Nanning'),
    ({'country': ' Singapore ', 'state': 'Singapore', 'city': 'Singapore'}, 'Singapore'),
    ({'city': 'Paris', 'latitude': 48.86, 'longitude': 2.35}, 'Paris'),
    ({'city': None, 'country': 42}, None),
])
async def test_location_uses_existing_place_names_only(exif, expected):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=[
        {'id': ID, 'type': 'IMAGE', 'visibility': 'timeline', 'exifInfo': exif}
    ]))) as http:
        photos = await ImmichClient(CFG, http).list_photos()
        assert photos[0]['location'] == expected

@pytest.mark.parametrize('visibility', ['timeline', 'archive', 'hidden'])
async def test_album_excludes_locked_assets_but_keeps_known_nonlocked_states(visibility):
    cfg = load_settings({'IMMICH_URL': 'https://nas.example', 'IMMICH_API_KEY': 'unit-test-secret', 'IMMICH_ALBUM_ID': ID})
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={'assets': [
        {'id': ID, 'type': 'IMAGE', 'visibility': 'locked'},
        {'id': '00000000-0000-0000-0000-000000000002', 'type': 'IMAGE', 'visibility': visibility},
    ]}))) as http:
        assert await ImmichClient(cfg, http).list_photos() == [
            {'id': '00000000-0000-0000-0000-000000000002', 'taken_date': None, 'location': None},
        ]
