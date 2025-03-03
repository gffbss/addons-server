# -*- coding: utf-8 -*-
from dateutil.parser import parse as parse_dt
import re
from urlparse import urlparse

from django.conf import settings
from django.core.cache import cache
from django.test.utils import override_settings
from django.utils import http as urllib
from django.utils.translation import trim_whitespace

import pytest
from jingo.helpers import datetime as datetime_filter
import mock
from nose.tools import eq_, assert_raises, nottest
from pyquery import PyQuery as pq

from olympia import amo
from olympia.amo.tests import TestCase, ESTestCaseWithAddons
from olympia.amo.urlresolvers import reverse
from olympia.amo.helpers import absolutify, numberfmt, urlparams
from olympia.addons.tests.test_views import TestMobile
from olympia.addons.models import (
    Addon, AddonCategory, Category, AppSupport, FrozenAddon, Persona)
from olympia.bandwagon.models import (
    Collection, CollectionAddon, FeaturedCollection)
from olympia.browse import feeds
from olympia.browse.views import (
    AddonFilter, locale_display_name, MIN_COUNT_FOR_LANDING,
    PAGINATE_PERSONAS_BY, ThemeFilter)
from olympia.constants.applications import THUNDERBIRD
from olympia.translations.models import Translation
from olympia.users.models import UserProfile
from olympia.versions.models import Version


pytestmark = pytest.mark.django_db


@nottest
def test_listing_sort(self, sort, key=None, reverse=True, sel_class='opt'):
    r = self.client.get(self.url, dict(sort=sort))
    eq_(r.status_code, 200)
    sel = pq(r.content)('#sorter ul > li.selected')
    eq_(sel.find('a').attr('class'), sel_class)
    eq_(r.context['sorting'], sort)
    a = list(r.context['addons'].object_list)
    if key:
        eq_(a, sorted(a, key=lambda x: getattr(x, key), reverse=reverse))
    return a


@nottest
def test_default_sort(self, sort, key=None, reverse=True, sel_class='opt'):
    r = self.client.get(self.url)
    eq_(r.status_code, 200)
    eq_(r.context['sorting'], sort)

    r = self.client.get(self.url, dict(sort='xxx'))
    eq_(r.status_code, 200)
    eq_(r.context['sorting'], sort)
    test_listing_sort(self, sort, key, reverse, sel_class)


class ExtensionTestCase(ESTestCaseWithAddons):

    def setUp(self):
        super(ExtensionTestCase, self).setUp()
        self.url = reverse('browse.es.extensions')


class TestUpdatedSort(ExtensionTestCase):

    # This needs to run in its own class for isolation.
    def test_updated_sort(self):
        r = self.client.get(urlparams(self.url, sort='updated'))
        addons = r.context['addons'].object_list
        assert list(addons)
        eq_(list(addons),
            sorted(addons, key=lambda x: x.last_updated, reverse=True))


class TestESExtensions(ExtensionTestCase):

    def test_landing(self):
        r = self.client.get(self.url)
        self.assertTemplateUsed(r, 'browse/extensions.html')
        self.assertTemplateUsed(r, 'addons/impala/listing/items.html')
        eq_(r.context['sorting'], 'popular')
        eq_(r.context['category'], None)
        doc = pq(r.content)
        eq_(doc('body').hasClass('s-featured'), True)
        eq_(doc('.addon-listing .listview').length, 0)

    def test_name_sort(self):
        r = self.client.get(urlparams(self.url, sort='name'))
        addons = r.context['addons'].object_list
        assert list(addons)
        eq_(list(addons), sorted(addons, key=lambda x: x.name))

    def test_created_sort(self):
        r = self.client.get(urlparams(self.url, sort='created'))
        addons = r.context['addons'].object_list
        assert list(addons)
        eq_(list(addons),
            sorted(addons, key=lambda x: x.created, reverse=True))

    def test_popular_sort(self):
        r = self.client.get(urlparams(self.url, sort='popular'))
        addons = r.context['addons'].object_list
        assert list(addons)
        eq_(list(addons),
            sorted(addons, key=lambda x: x.weekly_downloads, reverse=True))

    def test_rating_sort(self):
        r = self.client.get(urlparams(self.url, sort='rating'))
        addons = r.context['addons'].object_list
        assert list(addons)
        eq_(list(addons),
            sorted(addons, key=lambda x: x.bayesian_rating, reverse=True))

    def test_category(self):
        # Stick one add-on in a category, make sure search finds it.
        addon = Addon.objects.filter(status=amo.STATUS_PUBLIC,
                                     disabled_by_user=False)[0]
        c = Category.objects.create(application=amo.FIREFOX.id,
                                    slug='alerts', type=addon.type)
        AddonCategory.objects.create(category=c, addon=addon)
        addon.save()
        self.refresh()

        cat_url = reverse('browse.es.extensions', args=['alerts'])
        r = self.client.get(urlparams(cat_url))
        eq_(r.status_code, 200)
        addons = r.context['addons'].object_list
        eq_(list(addons), [addon])

    def test_invalid_sort(self):
        r = self.client.get(urlparams(self.url, sort='wut'))
        addons = r.context['addons'].object_list
        assert list(addons)
        eq_(list(addons),
            sorted(addons, key=lambda x: x.weekly_downloads, reverse=True))


def test_locale_display_name():

    def check(locale, english, native):
        actual = locale_display_name(locale)
        eq_(actual, (english, native))

    check('el', 'Greek', u'Ελληνικά')
    check('el-XX', 'Greek', u'Ελληνικά')
    assert_raises(KeyError, check, 'fake-lang', '', '')


class TestListing(TestCase):
    fixtures = ['base/appversion', 'base/users', 'base/category',
                'base/featured', 'addons/featured', 'addons/listed',
                'base/collections', 'bandwagon/featured_collections',
                'base/addon_3615']

    def setUp(self):
        super(TestListing, self).setUp()
        cache.clear()
        self.url = reverse('browse.extensions')

    def test_default_sort(self):
        r = self.client.get(self.url)
        eq_(r.context['sorting'], 'featured')

    def test_featured_sort(self):
        r = self.client.get(urlparams(self.url, sort='featured'))
        sel = pq(r.content)('#sorter ul > li.selected')
        eq_(sel.find('a').attr('class'), 'opt')
        eq_(sel.text(), 'Featured')

    def test_mostusers_sort(self):
        r = self.client.get(urlparams(self.url, sort='users'))
        sel = pq(r.content)('#sorter ul > li.selected')
        eq_(sel.find('a').attr('class'), 'opt')
        eq_(sel.text(), 'Most Users')
        a = r.context['addons'].object_list
        eq_(list(a),
            sorted(a, key=lambda x: x.average_daily_users, reverse=True))

    def test_toprated_sort(self):
        r = self.client.get(urlparams(self.url, sort='rating'))
        sel = pq(r.content)('#sorter ul > li.selected')
        eq_(sel.find('a').attr('class'), 'opt')
        eq_(sel.text(), 'Top Rated')
        a = r.context['addons'].object_list
        eq_(list(a), sorted(a, key=lambda x: x.bayesian_rating, reverse=True))

    def test_newest_sort(self):
        r = self.client.get(urlparams(self.url, sort='created'))
        sel = pq(r.content)('#sorter ul > li.selected')
        eq_(sel.find('a').attr('class'), 'opt')
        eq_(sel.text(), 'Newest')
        a = r.context['addons'].object_list
        eq_(list(a), sorted(a, key=lambda x: x.created, reverse=True))

    def test_name_sort(self):
        r = self.client.get(urlparams(self.url, sort='name'))
        sel = pq(r.content)('#sorter ul > li.selected')
        eq_(sel.find('a').attr('class'), 'extra-opt')
        eq_(sel.text(), 'Name')
        a = r.context['addons'].object_list
        eq_(list(a), sorted(a, key=lambda x: x.name))

    def test_weeklydownloads_sort(self):
        r = self.client.get(urlparams(self.url, sort='popular'))
        sel = pq(r.content)('#sorter ul > li.selected')
        eq_(sel.find('a').attr('class'), 'extra-opt')
        eq_(sel.text(), 'Weekly Downloads')
        a = r.context['addons'].object_list
        eq_(list(a), sorted(a, key=lambda x: x.weekly_downloads, reverse=True))

    def test_updated_sort(self):
        r = self.client.get(urlparams(self.url, sort='updated'))
        sel = pq(r.content)('#sorter ul > li.selected')
        eq_(sel.find('a').attr('class'), 'extra-opt')
        eq_(sel.text(), 'Recently Updated')
        a = r.context['addons'].object_list
        eq_(list(a), sorted(a, key=lambda x: x.last_updated, reverse=True))

    def test_upandcoming_sort(self):
        r = self.client.get(urlparams(self.url, sort='hotness'))
        sel = pq(r.content)('#sorter ul > li.selected')
        eq_(sel.find('a').attr('class'), 'extra-opt')
        eq_(sel.text(), 'Up & Coming')
        a = r.context['addons'].object_list
        eq_(list(a), sorted(a, key=lambda x: x.hotness, reverse=True))

    def test_added_date(self):
        doc = pq(self.client.get(urlparams(self.url, sort='created')).content)
        for item in doc('.items .item'):
            item = pq(item)
            addon_id = item('.install').attr('data-addon')
            ts = Addon.objects.get(id=addon_id).created
            eq_(item('.updated').text(),
                u'Added %s' % trim_whitespace(datetime_filter(ts)))

    def test_updated_date(self):
        doc = pq(self.client.get(urlparams(self.url, sort='updated')).content)
        for item in doc('.items .item'):
            item = pq(item)
            addon_id = item('.install').attr('data-addon')
            ts = Addon.objects.get(id=addon_id).last_updated
            eq_(item('.updated').text(),
                u'Updated %s' % trim_whitespace(datetime_filter(ts)))

    def test_users_adu_unit(self):
        doc = pq(self.client.get(urlparams(self.url, sort='users')).content)
        for item in doc('.items .item'):
            item = pq(item)
            addon_id = item('.install').attr('data-addon')
            adu = Addon.objects.get(id=addon_id).average_daily_users
            eq_(item('.adu').text(),
                '%s user%s' % (numberfmt(adu), 's' if adu != 1 else ''))

    def test_popular_adu_unit(self):
        doc = pq(self.client.get(urlparams(self.url, sort='popular')).content)
        for item in doc('.items .item'):
            item = pq(item)
            addon_id = item('.install').attr('data-addon')
            adu = Addon.objects.get(id=addon_id).weekly_downloads
            eq_(item('.adu').text(),
                '%s weekly download%s' % (numberfmt(adu),
                                          's' if adu != 1 else ''))

    def test_seeall_link_should_have_a_sort(self):
        category = Category.objects.get(pk=1)
        url = reverse('browse.extensions', kwargs={'category': category.slug})
        response = self.client.get(url)
        self.assertTemplateUsed(response,
                                "browse/impala/category_landing.html")
        doc = pq(response.content)
        assert "sort=popular" in doc('.seeall a').attr('href')


class TestLanguageTools(TestCase):
    fixtures = ['browse/test_views']

    def setUp(self):
        super(TestLanguageTools, self).setUp()
        cache.clear()
        self.url = reverse('browse.language-tools')
        response = self.client.get(self.url, follow=True)
        self.locales = list(response.context['locales'])

    def test_sorting(self):
        """The locales should be sorted by English display name."""
        displays = [locale.display for _, locale in self.locales]
        eq_(displays, sorted(displays))

    def test_native_missing_region(self):
        """
        If we had to strip a locale's region to find a display name, we
        append it to the native name for disambiguation.
        """
        el = dict(self.locales)['el-XX']
        assert el.native.endswith(' (el-xx)')

    def test_missing_locale(self):
        """If we don't know about a locale, show the addon name and locale."""
        wa = dict(self.locales)['wa']
        eq_(wa.display, 'Walloon Language Pack (wa)')
        eq_(wa.native, '')

    def test_packs_and_dicts(self):
        ca = dict(self.locales)['ca-valencia']
        eq_(len(ca.dicts), 1)
        eq_(len(ca.packs), 3)

    def test_empty_target_locale(self):
        """Make sure nothing breaks with empty target locales."""
        for addon in Addon.objects.all():
            addon.target_locale = ''
            addon.save()
        response = self.client.get(self.url, follow=True)
        eq_(response.status_code, 200)
        eq_(list(response.context['locales']), [])

    def test_null_target_locale(self):
        """Make sure nothing breaks with null target locales."""
        for addon in Addon.objects.all():
            addon.target_locale = None
            addon.save()
        response = self.client.get(self.url, follow=True)
        eq_(response.status_code, 200)
        eq_(list(response.context['locales']), [])


class TestThemes(TestCase):
    fixtures = ('base/category', 'base/addon_6704_grapple', 'base/addon_3615')

    def setUp(self):
        super(TestThemes, self).setUp()
        # Make all the add-ons themes.
        for addon in Addon.objects.all():
            addon.type = amo.ADDON_THEME
            addon.save()
        for category in Category.objects.all():
            category.type = amo.ADDON_THEME
            category.save()
        self.url = reverse('browse.themes')

    def test_unreviewed(self):
        pop = urlparams(self.url, sort='popular')

        # Only 3 without unreviewed.
        response = self.client.get(pop)
        eq_(len(response.context['addons'].object_list), 2)

        response = self.client.get(pop)
        eq_(len(response.context['addons'].object_list), 2)

    def test_default_sort(self):
        test_default_sort(self, 'users', 'average_daily_users')

    def test_rating_sort(self):
        test_listing_sort(self, 'rating', 'bayesian_rating')

    def test_newest_sort(self):
        test_listing_sort(self, 'created', 'created')

    def test_name_sort(self):
        test_listing_sort(self, 'name', 'name', reverse=False,
                          sel_class='extra-opt')

    def test_featured_sort(self):
        test_listing_sort(self, 'featured', reverse=False,
                          sel_class='opt')

    def test_downloads_sort(self):
        test_listing_sort(self, 'popular', 'weekly_downloads',
                          sel_class='extra-opt')

    def test_updated_sort(self):
        test_listing_sort(self, 'updated', 'last_updated',
                          sel_class='extra-opt')

    def test_upandcoming_sort(self):
        test_listing_sort(self, 'hotness', 'hotness', sel_class='extra-opt')

    def test_category_sidebar(self):
        c = Category.objects.filter(weight__gte=0).values_list('id', flat=True)
        doc = pq(self.client.get(self.url).content)
        for id in c:
            eq_(doc('#side-categories #c-%s' % id).length, 1)


class TestFeeds(TestCase):
    fixtures = ['base/appversion', 'base/users', 'base/category',
                'base/featured', 'addons/featured', 'addons/listed',
                'base/collections', 'bandwagon/featured_collections',
                'base/addon_3615']

    def setUp(self):
        super(TestFeeds, self).setUp()
        cache.clear()
        self.url = reverse('browse.extensions')
        self.rss_url = reverse('browse.extensions.rss')
        self.filter = AddonFilter

    def _check_feed(self, browse_url, rss_url, sort='featured'):
        """
        Check RSS feed URLs and that the results on the listing pages match
        those for their respective RSS feeds.
        """
        # Check URLs.
        r = self.client.get(browse_url, follow=True)
        doc = pq(r.content)
        rss_url += '?sort=%s' % sort
        eq_(doc('link[type="application/rss+xml"]').attr('href'), rss_url)
        eq_(doc('#subscribe').attr('href'), rss_url)

        # Ensure that the RSS items match those on the browse listing pages.
        r = self.client.get(rss_url)
        rss_doc = pq(r.content)
        pg_items = doc('.items .item')
        rss_items = rss_doc('item')
        items_urls = zip(
            sorted((absolutify(pq(x).find('h3 a').attr('href')), pq(x))
                   for x in pg_items),
            sorted((pq(x).find('link').text(), pq(x)) for x in rss_items))
        for (pg_url, pg_item), (rss_url, rss_item) in items_urls:
            abs_url = pg_url.split('?')[0]
            assert rss_url.endswith(abs_url), 'Unexpected URL: %s' % abs_url
            if sort in ('added', 'updated'):
                # Check timestamps.
                pg_ts = pg_item.find('.updated').text().strip('Added Updated')
                rss_ts = rss_item.find('pubDate').text()
                # Look at YMD, since we don't have h:m on listing pages.
                eq_(parse_dt(pg_ts).isocalendar(),
                    parse_dt(rss_ts).isocalendar())

    def _check_sort_urls(self, items, opts):
        items = sorted(items, key=lambda x: x.get('href'))
        options = getattr(self.filter, opts)
        options = sorted(options, key=lambda x: x[0])
        for item, options in zip(items, options):
            item = pq(item)
            slug, title = options
            url = '%s?sort=%s' % (self.url, slug)
            eq_(item.attr('href'), url)
            eq_(item.text(), unicode(title))
            self._check_feed(url, self.rss_url, slug)

    def test_extensions_feed(self):
        eq_(self.client.get(self.rss_url).status_code, 200)

    def test_themes_feed(self):
        Addon.objects.update(type=amo.ADDON_THEME)
        Category.objects.update(type=amo.ADDON_THEME)
        r = self.client.get(reverse('browse.themes.rss',
                                    args=['alerts-updates']))
        eq_(r.status_code, 200)

    def test_extensions_sort_opts_urls(self):
        r = self.client.get(self.url, follow=True)
        s = pq(r.content)('#sorter')
        self._check_feed(self.url, self.rss_url, 'featured')
        self._check_sort_urls(s.find('a.opt'), 'opts')
        self._check_sort_urls(s.find('a.extra-opt'), 'extras')

    def test_themes_sort_opts_urls(self):
        r = self.client.get(reverse('browse.themes'))
        eq_(r.status_code, 200)
        doc = pq(r.content)
        eq_(doc('#sorter').length, 1)
        eq_(doc('#subscribe').length, 0)

        Addon.objects.update(type=amo.ADDON_THEME)
        Category.objects.update(type=amo.ADDON_THEME)

        self.url = reverse('browse.themes', args=['alerts-updates'])
        self.rss_url = reverse('browse.themes.rss', args=['alerts-updates'])
        self.filter = ThemeFilter
        r = self.client.get(self.url, follow=True)
        s = pq(r.content)('#sorter')
        self._check_feed(self.url, self.rss_url, 'users')
        self._check_sort_urls(s.find('a.opt'), 'opts')
        self._check_sort_urls(s.find('a.extra-opt'), 'extras')


class TestFeaturedLocale(TestCase):
    fixtures = ['base/appversion', 'base/category', 'base/users',
                'base/addon_3615', 'base/featured', 'addons/featured',
                'browse/nameless-addon', 'base/collections',
                'bandwagon/featured_collections',
                'base/addon_3615_featuredcollection']

    def setUp(self):
        super(TestFeaturedLocale, self).setUp()
        self.addon = Addon.objects.get(pk=3615)
        self.persona = Addon.objects.get(pk=15679)
        self.extension = Addon.objects.get(pk=2464)
        self.category = Category.objects.get(slug='bookmarks')
        self.url = urlparams(reverse('browse.extensions', args=['bookmarks']),
                             {}, sort='featured')
        cache.clear()

    def reset(self):
        cache.clear()

    def list_featured(self, content):
        # Not sure we want to get into testing randomness
        # between multiple executions of a page, but if this is a quick
        # way to print out the results and check yourself that they
        # are changing.
        doc = pq(content)
        ass = doc('.featured-inner .item a')
        rx = re.compile('/(en-US|es)/firefox/addon/(\d+)/$')
        for a in ass:
            mtch = rx.match(a.attrib['href'])
            if mtch:
                print mtch.group(2)

    def test_creatured_locale_en_US(self):
        res = self.client.get(self.url, follow=True)
        assert self.addon in res.context['addons']

    def test_creatured_locale_es_ES(self):
        """Ensure 'en-US'-creatured add-ons do not exist for other locales."""
        res = self.client.get(self.url.replace('en-US', 'es'), follow=True)
        assert self.addon not in res.context['addons']

    def test_creatured_locale_nones(self):
        self.change_addoncategory(self.addon, '')
        res = self.client.get(self.url, follow=True)
        assert self.addon in res.context['addons']

        self.change_addoncategory(self.addon, None)
        res = self.client.get(self.url, follow=True)
        assert self.addon in res.context['addons']

    def test_creatured_locale_many(self):
        self.change_addoncategory(self.addon, 'en-US,es')
        res = self.client.get(self.url, follow=True)
        assert self.addon in res.context['addons']

        res = self.client.get(self.url.replace('en-US', 'es'), follow=True)
        assert self.addon in res.context['addons']

    def test_creatured_locale_not_en_US(self):
        self.change_addoncategory(self.addon, 'es')
        res = self.client.get(self.url, follow=True)
        assert self.addon not in res.context['addons']

    def test_featured_locale_en_US(self):
        res = self.client.get(reverse('browse.extensions') + '?sort=featured')
        assert self.extension in res.context['addons']

    def test_featured_locale_not_persona_en_US(self):
        res = self.client.get(reverse('browse.extensions') + '?sort=featured')
        assert self.persona not in res.context['addons']

    def test_featured_locale_es_ES(self):
        self.change_addon(self.extension, 'es')
        url = reverse('browse.extensions') + '?sort=featured'
        res = self.client.get(url)
        assert self.extension not in res.context['addons']

        res = self.client.get(url.replace('en-US', 'es'))
        self.change_addon(self.extension, 'es')
        assert self.extension in res.context['addons']

    def test_featured_extensions_no_category_en_US(self):
        addon = self.extension
        res = self.client.get(reverse('browse.extensions'))
        assert addon in res.context['addons'].object_list

    def test_featured_extensions_with_category_es_ES(self):
        addon = self.addon
        res = self.client.get(reverse('browse.extensions', args=['bookmarks']))
        assert addon in res.context['filter'].all()['featured']

        self.change_addoncategory(addon, 'es')
        res = self.client.get(reverse('browse.extensions', args=['bookmarks']))
        assert addon not in res.context['filter'].all()['featured']

    def test_featured_persona_no_category_en_US(self):
        addon = self.persona
        url = reverse('browse.personas')
        res = self.client.get(url)
        assert addon in res.context['featured']

        self.change_addon(addon, 'es')
        res = self.client.get(url)
        assert addon not in res.context['featured']

        res = self.client.get(url.replace('en-US', 'es'))
        assert addon in res.context['featured']

    def test_featured_persona_category_en_US(self):
        addon = self.persona
        category = Category.objects.get(id=22)
        category.update(type=amo.ADDON_PERSONA)

        addon.addoncategory_set.create(category=category, feature=True)
        self.reset()
        url = reverse('browse.personas', args=[category.slug])
        res = self.client.get(url)
        assert addon in res.context['featured']

        self.change_addoncategory(addon, 'es')
        res = self.client.get(url)
        assert addon not in res.context['featured']

        res = self.client.get(url.replace('en-US', 'es'))
        assert addon in res.context['featured']

    def test_homepage(self):
        url = reverse('home')
        res = self.client.get(url)
        assert self.extension in res.context['featured']

        self.change_addon(self.extension, 'es')
        res = self.client.get(url)
        assert self.extension not in res.context['featured']

        res = self.client.get(url.replace('en-US', 'es'))
        assert self.extension in res.context['featured']

    def test_homepage_persona(self):
        res = self.client.get(reverse('home'))
        assert self.persona not in res.context['featured']

    def test_homepage_filter(self):
        # Ensure that the base homepage filter is applied.
        res = self.client.get(reverse('home'))
        listed = [p.pk for p in (Addon.objects
                                      .listed(amo.FIREFOX)
                                      .exclude(type=amo.ADDON_PERSONA))]

        featured = Addon.featured_random(amo.FIREFOX, 'en-US')
        actual = [p.pk for p in res.context['featured']]

        eq_(sorted(actual), sorted(set(listed) & set(featured)))

    def test_homepage_listed_single(self):
        listed = [p.pk for p in Addon.objects.listed(amo.FIREFOX)]
        eq_(listed.count(7661), 1)
        addon = Addon.objects.get(pk=7661)
        addon.update(status=amo.STATUS_PUBLIC)
        listed = [p.pk for p in Addon.objects.listed(amo.FIREFOX)]
        eq_(listed.count(7661), 1)

    def test_homepage_order(self):
        FeaturedCollection.objects.filter(collection__addons=3615)[0].delete()

        # Make these apps listed.
        for pk in [1003, 3481]:
            addon = Addon.objects.get(pk=pk)
            addon.update(status=amo.STATUS_PUBLIC)
            addon.appsupport_set.create(app=1)

        # Note 1003 and 3481 are now en-US.
        # And 7661 and 2464 are now None.
        # The order should be random within those boundaries.
        another = Addon.objects.get(id=1003)
        self.change_addon(another, 'en-US')
        cache.clear()

        url = reverse('home')
        res = self.client.get(url)
        items = res.context['featured']

        eq_([1003, 3481], sorted([i.pk for i in items[0:2]]))
        eq_([2464, 7661], sorted([i.pk for i in items[2:]]))

        res = self.client.get(url.replace('en-US', 'es'))
        items = res.context['featured']
        eq_([2464, 7661], sorted([i.pk for i in items]))

        self.change_addon(another, 'es')

        res = self.client.get(url.replace('en-US', 'es'))
        items = res.context['featured']
        eq_(items[0].pk, 1003)
        eq_([1003, 2464, 7661], sorted([i.pk for i in items]))

    def test_featured_ids(self):
        FeaturedCollection.objects.filter(collection__addons=3615)[0].delete()

        another = Addon.objects.get(id=1003)
        self.change_addon(another, 'en-US')
        items = Addon.featured_random(amo.FIREFOX, 'en-US')

        # The order should be random within those boundaries.
        eq_([1003, 3481], sorted(items[0:2]))
        eq_([1001, 2464, 7661, 15679], sorted(items[2:]))

    def change_addon(self, addon, locale='es'):
        fc = FeaturedCollection.objects.filter(collection__addons=addon.id)[0]
        feature = FeaturedCollection.objects.create(
            locale=locale, application=amo.FIREFOX.id,
            collection=Collection.objects.create())
        c = CollectionAddon.objects.filter(addon=addon,
                                           collection=fc.collection)[0]
        c.collection = feature.collection
        c.save()
        self.reset()

    def change_addoncategory(self, addon, locale='es'):
        CollectionAddon.objects.filter(addon=addon).delete()
        locales = (locale or '').split(',')
        for locale in locales:
            c = CollectionAddon.objects.create(
                addon=addon, collection=Collection.objects.create())
            FeaturedCollection.objects.create(
                locale=locale, application=amo.FIREFOX.id,
                collection=c.collection)
        self.reset()


class TestListingByStatus(TestCase):
    fixtures = ['base/addon_3615']

    def setUp(self):
        super(TestListingByStatus, self).setUp()
        self.addon = Addon.objects.get(id=3615)

    def get_addon(self, addon_status, file_status):
        self.addon.current_version.all_files[0].update(status=file_status)
        self.addon.update(status=addon_status, _current_version=None)
        self.addon.update_version()
        return Addon.objects.get(id=3615)

    def check(self, exp):
        r = self.client.get(reverse('browse.extensions') + '?sort=created')
        addons = list(r.context['addons'].object_list)
        eq_(addons, exp)

    def test_public_public_listed(self):
        self.get_addon(amo.STATUS_PUBLIC, amo.STATUS_PUBLIC)
        self.check([self.addon])

    def test_public_nom_unlisted(self):
        self.get_addon(amo.STATUS_PUBLIC, amo.STATUS_NOMINATED)
        self.check([])

    def test_public_lite_unlisted(self):
        self.get_addon(amo.STATUS_PUBLIC, amo.STATUS_LITE)
        self.check([])

    def test_lite_unreviewed_unlisted(self):
        self.get_addon(amo.STATUS_LITE, amo.STATUS_UNREVIEWED)
        self.check([])

    def test_lite_lite_listed(self):
        self.get_addon(amo.STATUS_LITE, amo.STATUS_LITE)
        self.check([self.addon])

    def test_lite_lan_listed(self):
        self.get_addon(amo.STATUS_LITE, amo.STATUS_LITE_AND_NOMINATED)
        self.check([self.addon])

    def test_lan_unreviewed_unlisted(self):
        self.get_addon(amo.STATUS_LITE_AND_NOMINATED, amo.STATUS_UNREVIEWED)
        self.check([])

    def test_lan_lite_listed(self):
        self.get_addon(amo.STATUS_LITE_AND_NOMINATED, amo.STATUS_LITE)
        self.check([self.addon])

    def test_lan_public_listed(self):
        self.get_addon(amo.STATUS_LITE_AND_NOMINATED, amo.STATUS_PUBLIC)
        self.check([self.addon])

    def test_unreviewed_public_unlisted(self):
        self.get_addon(amo.STATUS_UNREVIEWED, amo.STATUS_PUBLIC)
        self.check([])

    def test_nom_public_unlisted(self):
        self.get_addon(amo.STATUS_NOMINATED, amo.STATUS_PUBLIC)
        self.check([])


class BaseSearchToolsTest(TestCase):
    fixtures = ('base/appversion', 'base/featured',
                'addons/featured', 'base/category', 'addons/listed')

    def setUp(self):
        super(BaseSearchToolsTest, self).setUp()
        # Transform bookmarks into a search category:
        Category.objects.filter(slug='bookmarks').update(type=amo.ADDON_SEARCH)

    def setup_tools_and_extensions(self):
        # Pretend all Add-ons are search-related:
        Addon.objects.update(type=amo.ADDON_SEARCH)

        # One will be an extension in the search category:
        limon = Addon.objects.get(
            name__localized_string='Limon free English-Hebrew dictionary')
        limon.type = amo.ADDON_EXTENSION
        limon.status = amo.STATUS_PUBLIC
        limon.save()
        AppSupport(addon=limon, app=amo.FIREFOX.id).save()

        # Another will be a search add-on in the search category:
        readit = Addon.objects.get(name__localized_string='Read It Later')
        readit.type = amo.ADDON_SEARCH
        readit.status = amo.STATUS_PUBLIC
        readit.save()

        cache.clear()


class TestSearchToolsPages(BaseSearchToolsTest):

    def test_landing_page(self):
        self.setup_tools_and_extensions()
        response = self.client.get(reverse('browse.search-tools'))
        eq_(response.status_code, 200)
        doc = pq(response.content)

        # Should have add-ons ordered by popularity (weekly downloads):
        eq_([a.name.localized_string
             for a in response.context['addons'].object_list],
            [u'FoxyProxy Standard', u'Read It Later', u'Lady Gaga'])

        # Ensure that all heading links have the proper base URL
        # between the category / no category cases.
        sort_links = [urlparse(a.attrib['href']).path for a in
                      doc('.listing-header ul li a')]
        eq_(set(sort_links), set([reverse('browse.search-tools')]))

    def test_sidebar_extensions_links(self):
        response = self.client.get(reverse('browse.search-tools'))
        eq_(response.status_code, 200)
        doc = pq(response.content)

        links = doc('#search-tools-sidebar a')

        eq_(sorted([a.text.strip() for a in links]),
            sorted(['Most Popular', 'Recently Added',  # Search Extensions.
                    'Bookmarks']))  # Search Providers.

        search_ext_url = urlparse(reverse('browse.extensions',
                                  kwargs=dict(category='search-tools')))

        eq_(urlparse(links[0].attrib['href']).path, search_ext_url.path)
        eq_(urlparse(links[1].attrib['href']).path, search_ext_url.path)

    def test_additional_resources(self):
        for prefix, app in (
                ('/en-US/firefox', amo.FIREFOX.pretty),
                ('/en-US/seamonkey', amo.SEAMONKEY.pretty)):
            app = unicode(app)  # get the proxied unicode obj
            response = self.client.get('%s/search-tools/' % prefix)
            eq_(response.status_code, 200)
            doc = pq(response.content)
            txt = doc('#additional-resources ul li:eq(0)').text()
            assert txt.endswith(app), "Expected %r got: %r" % (app, txt)

    def test_search_tools_arent_friends_with_everyone(self):
        # Search tools only show up for Firefox
        response = self.client.get('/en-US/thunderbird/search-tools/')
        doc = pq(response.content)
        assert not doc('#search-tools-sidebar')

    def test_other_pages_exclude_extensions(self):
        # pretend all Add-ons are search-related:
        Addon.objects.update(type=amo.ADDON_SEARCH)
        # randomly make one an extension to be sure it is filtered out:
        Addon.objects.valid()[0].update(type=amo.ADDON_EXTENSION)

        for sort_key in ('name', 'updated', 'created', 'popular', 'rating'):
            url = reverse('browse.search-tools') + '?sort=' + sort_key
            r = self.client.get(url)
            all_addons = r.context['addons'].object_list
            assert len(all_addons)
            for addon in all_addons:
                assert addon.type == amo.ADDON_SEARCH, (
                    "sort=%s; Unexpected Add-on type for %r" % (
                        sort_key, addon))

    def test_rss_links_per_page(self):

        def get_link(url):
            r = self.client.get(url)
            eq_(r.status_code, 200)
            doc = pq(r.content)
            return doc('head link[type="application/rss+xml"]').attr('href')

        eq_(get_link(reverse('browse.search-tools')),
            reverse('browse.search-tools.rss') + '?sort=popular')

        eq_(get_link(reverse('browse.search-tools') + '?sort=name'),
            reverse('browse.search-tools.rss') + '?sort=name')

        eq_(get_link(reverse('browse.search-tools', args=('bookmarks',))),
            reverse('browse.search-tools.rss',
                    args=('bookmarks',)) + '?sort=popular')


class TestSearchToolsFeed(BaseSearchToolsTest):

    def test_created_search_tools(self):
        self.setup_tools_and_extensions()
        url = reverse('browse.search-tools.rss') + '?sort=created'
        r = self.client.get(url)
        eq_(r.status_code, 200)
        doc = pq(r.content)

        eq_(doc('rss channel title')[0].text,
            'Search Tools :: Add-ons for Firefox')
        link = doc('rss channel link')[0].text
        rel_link = reverse('browse.search-tools.rss') + '?sort=created'
        assert link.endswith(rel_link), ('Unexpected link: %r' % link)
        eq_(doc('rss channel description')[0].text, "Search tools")

        # There should be tools ordered by created date.
        eq_([e.text for e in doc('rss channel item title')],
            ['Lady Gaga 0', 'Read It Later 2.0.3', 'FoxyProxy Standard 2.17'])

    def test_search_tools_no_sorting(self):
        url = reverse('browse.search-tools.rss')
        r = self.client.get(url)
        eq_(r.status_code, 200)
        doc = pq(r.content)

        link = doc('rss channel link')[0].text
        rel_link = reverse('browse.search-tools.rss') + '?sort=popular'
        assert link.endswith(rel_link), ('Unexpected link: %r' % link)

    def test_search_tools_by_name(self):
        # Pretend Foxy is a search add-on
        (Addon.objects.filter(name__localized_string='FoxyProxy Standard')
                      .update(type=amo.ADDON_SEARCH))

        url = reverse('browse.search-tools.rss') + '?sort=name'
        r = self.client.get(url)
        eq_(r.status_code, 200)
        doc = pq(r.content)

        eq_(doc('rss channel description')[0].text, 'Search tools')

        # There should be only search tools.
        eq_([e.text for e in doc('rss channel item title')],
            ['FoxyProxy Standard 2.17'])

    def test_search_tools_within_a_category(self):
        # Pretend Foxy is the only bookmarks related search add-on
        AddonCategory.objects.all().delete()
        foxy = Addon.objects.get(name__localized_string='FoxyProxy Standard')
        foxy.type = amo.ADDON_SEARCH
        foxy.save()
        bookmarks = Category.objects.get(slug='bookmarks')
        bookmarks.addoncategory_set.add(
            AddonCategory(addon=foxy, feature=False))
        bookmarks.save()

        url = reverse('browse.search-tools.rss',
                      args=('bookmarks',)) + '?sort=popular'
        r = self.client.get(url)
        eq_(r.status_code, 200)
        doc = pq(r.content)

        eq_(doc('rss channel title')[0].text,
            'Bookmarks :: Search Tools :: Add-ons for Firefox')

        link = doc('rss channel link')[0].text
        rel_link = reverse('browse.search-tools.rss',
                           args=('bookmarks',)) + '?sort=popular'
        assert link.endswith(rel_link), ('Unexpected link: %r' % link)

        eq_(doc('rss channel description')[0].text,
            "Search tools relating to Bookmarks")

        eq_([e.text for e in doc('rss channel item title')],
            ['FoxyProxy Standard 2.17'])

    def test_non_ascii_titles(self):
        bookmarks = Category.objects.get(slug='bookmarks')
        bookmarks.name = u'Ivan Krstić'
        bookmarks.save()

        url = reverse('browse.search-tools.rss',
                      args=('bookmarks',))
        r = self.client.get(url)
        eq_(r.status_code, 200)
        doc = pq(r.content)

        eq_(doc('rss channel title')[0].text,
            u'Ivan Krstić :: Search Tools :: Add-ons for Firefox')


class TestLegacyRedirects(TestCase):
    fixtures = ['base/category']

    def redirects(self, from_, to, status_code=301):
        r = self.client.get('/en-US/firefox' + from_)
        self.assert3xx(r, '/en-US/firefox' + to, status_code=status_code)

    def test_types(self):
        self.redirects('/browse/type:1', '/extensions/')
        self.redirects('/browse/type:1/', '/extensions/')
        self.redirects('/browse/type:1/cat:all', '/extensions/')
        self.redirects('/browse/type:1/cat:all/', '/extensions/')
        self.redirects('/browse/type:1/cat:72', '/extensions/alerts-updates/')
        self.redirects('/browse/type:1/cat:72/', '/extensions/alerts-updates/')
        self.redirects('/browse/type:1/cat:72/sort:newest/format:rss',
                       '/extensions/alerts-updates/format:rss?sort=created')
        self.redirects('/browse/type:1/cat:72/sort:weeklydownloads/format:rss',
                       '/extensions/alerts-updates/format:rss?sort=popular')

        Category.objects.get(id=72).update(type=amo.ADDON_THEME)
        self.redirects('/browse/type:2/cat:72/format:rss',
                       '/complete-themes/alerts-updates/format:rss')

        self.redirects('/browse/type:2', '/complete-themes/')
        self.redirects('/browse/type:3', '/language-tools/')
        self.redirects('/browse/type:4', '/search-tools/')
        self.redirects('/full-themes/', '/complete-themes/')
        self.redirects('/search-engines', '/search/?atype=4')
        # self.redirects('/browse/type:7', '/plugins/')
        self.redirects('/recommended', '/extensions/?sort=featured')
        self.redirects('/featured', '/extensions/?sort=featured')
        self.redirects('/recommended/format:rss', '/featured/format:rss')

    def test_complete_themes(self):
        # A former Theme category should get redirected to /full-themes/.
        cat = Category.objects.filter(slug='feeds-news-blogging')
        cat.update(type=amo.ADDON_THEME)

        self.redirects('/themes/feeds-news-blogging?sort=rating',
                       '/complete-themes/feeds-news-blogging?sort=rating')

        self.redirects(
            '/themes/feeds-news-blogging/format:rss?sort=users',
            '/complete-themes/feeds-news-blogging/format:rss?sort=users')

    def test_personas(self):
        cat = Category.objects.filter(slug='feeds-news-blogging')
        cat.update(type=amo.ADDON_PERSONA)

        self.redirects('/personas/', '/themes/')

        # A former Persona category should now live at /themes/.
        self.redirects('/personas/feeds-news-blogging?sort=rating',
                       '/themes/feeds-news-blogging?sort=rating')

        # The trailing slash should get stripped, yeah. We're just
        # testing that we don't redirect to /complete-themes/.
        self.redirects('/themes/feeds-news-blogging/?sort=rating',
                       '/themes/feeds-news-blogging?sort=rating')

    def test_creatured(self):
        self.redirects('/extensions/feeds-news-blogging/featured',
                       '/extensions/feeds-news-blogging/?sort=featured')

    def test_creatured_with_more_than_one_category_slug(self):
        Category.objects.create(application=THUNDERBIRD.id,
                                type=amo.ADDON_EXTENSION,
                                slug='feeds-news-blogging')
        self.redirects('/extensions/feeds-news-blogging/featured',
                       '/extensions/feeds-news-blogging/?sort=featured')

    def test_missing_rss_redirections_749754(self):
        url = '/en-US/firefox/browse/type:{type}/cat:1/format:rss?sort=updated'
        r = self.client.get(url.format(type=3))  # Language tools.
        eq_(r.status_code, 404)
        r = self.client.get(url.format(type=9))  # Themes.
        eq_(r.status_code, 404)


class TestCategoriesFeed(TestCase):

    def setUp(self):
        super(TestCategoriesFeed, self).setUp()
        self.feed = feeds.CategoriesRss()
        self.u = u'Ελληνικά'
        self.wut = Translation(localized_string=self.u, locale='el')

        self.feed.request = mock.Mock()
        self.feed.request.APP.pretty = self.u

        self.category = Category(name=self.u)

        self.addon = Addon(name=self.u, id=2, type=1, slug='xx')
        self.addon._current_version = Version(version='v%s' % self.u)

    def test_title(self):
        eq_(self.feed.title(self.category),
            u'%s :: Add-ons for %s' % (self.wut, self.u))

    def test_item_title(self):
        eq_(self.feed.item_title(self.addon),
            u'%s v%s' % (self.u, self.u))

    def test_item_guid(self):
        t = self.feed.item_guid(self.addon)
        url = u'/addon/%s/versions/v%s' % (self.addon.slug,
                                           urllib.urlquote(self.u))
        assert t.endswith(url), t


class TestFeaturedFeed(TestCase):
    fixtures = ['addons/featured', 'base/addon_3615',
                'base/appversion', 'base/appversion', 'base/collections',
                'base/featured', 'base/users',
                'bandwagon/featured_collections']

    def test_feed_elements_present(self):
        url = reverse('browse.featured.rss')
        r = self.client.get(url, follow=True)
        doc = pq(r.content)
        eq_(doc('rss channel title')[0].text,
            'Featured Add-ons :: Add-ons for Firefox')
        assert doc('rss channel link')[0].text.endswith('/en-US/firefox/')
        eq_(doc('rss channel description')[0].text,
            "Here's a few of our favorite add-ons to help you get started "
            "customizing Firefox.")
        eq_(len(doc('rss channel item')),
            Addon.objects.featured(amo.FIREFOX).count())


class TestPersonas(TestCase):
    fixtures = ('base/appversion', 'base/featured',
                'addons/featured', 'addons/persona')

    def setUp(self):
        super(TestPersonas, self).setUp()
        self.landing_url = reverse('browse.personas')
        self.upandcoming_url = '{path}?sort=up-and-coming'.format(
            path=self.landing_url)
        self.created_url = '{path}?sort=created'.format(path=self.landing_url)
        self.grid_template = 'browse/personas/grid.html'
        self.landing_template = 'browse/personas/category_landing.html'

    def create_personas(self, number, persona_extras=None):
        persona_extras = persona_extras or {}
        addon = Addon.objects.get(id=15679)
        for i in xrange(number):
            a = Addon(type=amo.ADDON_PERSONA)
            a.name = 'persona-%s' % i
            a.all_categories = []
            a.save()
            v = Version.objects.get(addon=addon)
            v.addon = a
            v.pk = None
            v.save()
            p = Persona(addon_id=a.id, persona_id=i, **persona_extras)
            p.save()
            a.persona = p
            a._current_version = v
            a.status = amo.STATUS_PUBLIC
            a.save()

    def test_personas_grid(self):
        """
        Show grid page if there are fewer than
        MIN_COUNT_FOR_LANDING+1 Personas.
        """
        base = Addon.objects.public().filter(type=amo.ADDON_PERSONA)
        eq_(base.count(), 2)
        r = self.client.get(self.landing_url)
        self.assertTemplateUsed(r, self.grid_template)
        eq_(r.status_code, 200)
        eq_(r.context['is_homepage'], True)

    def test_personas_landing(self):
        """
        Show landing page if there are greater than
        MIN_COUNT_FOR_LANDING popular Personas.
        """
        self.create_personas(MIN_COUNT_FOR_LANDING,
                             persona_extras={'popularity': 100})
        base = Addon.objects.public().filter(type=amo.ADDON_PERSONA)
        eq_(base.count(), MIN_COUNT_FOR_LANDING + 2)
        r = self.client.get(self.landing_url)
        self.assertTemplateUsed(r, self.landing_template)

        # Whatever the `category.count` is.
        category = Category(
            type=amo.ADDON_PERSONA, slug='abc',
            count=MIN_COUNT_FOR_LANDING + 1, application=amo.FIREFOX.id)
        category.save()
        r = self.client.get(self.landing_url)
        self.assertTemplateUsed(r, self.landing_template)

    def test_personas_grid_sorting(self):
        """Ensure we hit a grid page if there is a sorting."""
        category = Category(
            type=amo.ADDON_PERSONA, slug='abc', application=amo.FIREFOX.id)
        category.save()
        category_url = reverse('browse.personas', args=[category.slug])
        r = self.client.get(category_url + '?sort=created')
        self.assertTemplateUsed(r, self.grid_template)

        # Whatever the `category.count` is.
        category.update(count=MIN_COUNT_FOR_LANDING + 1)
        r = self.client.get(category_url + '?sort=created')
        self.assertTemplateUsed(r, self.grid_template)

    def test_personas_category_landing_frozen(self):
        # Check to make sure add-on is there.
        r = self.client.get(self.landing_url)

        personas = pq(r.content).find('.persona-preview')
        eq_(personas.length, 2)

        # Freeze the add-on
        FrozenAddon.objects.create(addon_id=15663)

        # Make sure it's not there anymore
        res = self.client.get(self.landing_url)

        personas = pq(res.content).find('.persona-preview')
        eq_(personas.length, 1)

    def test_only_popular_persona_are_shown_in_up_and_coming(self):
        r = self.client.get(self.upandcoming_url)
        personas = pq(r.content).find('.persona-preview')
        eq_(personas.length, 2)
        p = Persona.objects.get(pk=559)
        p.popularity = 99
        p.save()
        r = self.client.get(self.upandcoming_url)
        personas = pq(r.content).find('.persona-preview')
        eq_(personas.length, 1)

    @override_settings(PERSONA_DEFAULT_PAGES=2)
    def test_pagination_in_up_and_coming(self):
        # If the number is < MIN_COUNT_FOR_LANDING + 1 we keep
        # the base pagination.
        r = self.client.get(self.upandcoming_url)
        eq_(str(r.context['addons']), '<Page 1 of 1>')
        # Otherwise we paginate on 10, hardcoded.
        self.create_personas(PAGINATE_PERSONAS_BY,
                             persona_extras={'popularity': 100})
        r = self.client.get(self.upandcoming_url)
        eq_(str(r.context['addons']), '<Page 1 of 2>')
        # Even if the number of retrieved personas is higher than
        # 10 pages we shouldn't have a bump in page numbers.
        self.create_personas(
            PAGINATE_PERSONAS_BY * settings.PERSONA_DEFAULT_PAGES,
            persona_extras={'popularity': 100})
        r = self.client.get(self.upandcoming_url)
        eq_(str(r.context['addons']), '<Page 1 of 2>')

    def test_pagination_in_created(self):
        r = self.client.get(self.created_url)
        eq_(str(r.context['addons']), '<Page 1 of 1>')
        self.create_personas(PAGINATE_PERSONAS_BY)
        r = self.client.get(self.created_url)
        eq_(str(r.context['addons']), '<Page 1 of 2>')


class TestMobileFeatured(TestMobile):

    def test_featured(self):
        r = self.client.get(reverse('browse.extensions') + '?sort=featured')
        eq_(r.status_code, 200)
        self.assertTemplateUsed(r, 'browse/mobile/extensions.html')
        eq_(r.context['sorting'], 'featured')


class TestMobileExtensions(TestMobile):

    def test_extensions(self):
        r = self.client.get(reverse('browse.extensions'))
        eq_(r.status_code, 200)
        self.assertTemplateUsed(r, 'browse/mobile/extensions.html')
        self.assertTemplateUsed(r, 'addons/listing/items_mobile.html')
        eq_(r.context['category'], None)
        eq_(pq(r.content)('.addon-listing .listview').length, 1)

    def test_category_default_sort(self):
        cat = Category.objects.all()[0]
        url = reverse('browse.extensions', args=[cat.slug])
        r = self.client.get(url)
        eq_(r.status_code, 200)
        self.assertTemplateUsed(r, 'browse/mobile/extensions.html')
        self.assertTemplateUsed(r, 'addons/listing/items_mobile.html')
        eq_(r.context['sorting'], 'rating')
        eq_(r.context['category'], cat)
        doc = pq(r.content)
        eq_(doc('.addon-listing .listview').length, 1)
        eq_(doc('.addon-listing .listview li.item').length, 1)

    def test_category_sort_by_featured(self):
        cat = Category.objects.all()[0]
        url = reverse('browse.extensions', args=[cat.slug])
        url = "{0}?sort=featured".format(url)
        r = self.client.get(url)
        eq_(r.status_code, 200)
        self.assertTemplateUsed(r, 'browse/mobile/extensions.html')
        self.assertTemplateNotUsed(r, 'addons/listing/items_mobile.html')
        eq_(r.context['category'], cat)
        doc = pq(r.content)
        eq_(doc('.addon-listing .listview').length, 0)
        eq_(doc('.no-results').length, 1)


class TestMobileHeader(amo.tests.MobileTest, TestCase):
    fixtures = ['base/users']

    def setUp(self):
        super(TestMobileHeader, self).setUp()
        self.url = reverse('browse.extensions')

    def get_pq(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        return pq(r.content.decode('utf-8'))

    def test_header(self):
        nav = self.get_pq()('#auth-nav')
        eq_(nav.length, 1)
        eq_(nav.find('li.purchases').length, 0)
        eq_(nav.find('li.register').length, 1)
        eq_(nav.find('li.login').length, 1)

    def _test_auth_nav(self, expected):
        self.client.login(username='regular@mozilla.com', password='password')
        self.url = reverse('browse.extensions')
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        doc = pq(r.content.decode('utf-8'))
        amo.tests.check_links(expected, doc('#auth-nav li'))

    @amo.tests.mobile_test
    def test_mobile_auth_nav(self):
        expected = [
            (UserProfile.objects.get(username='regularuser').welcome_name,
             None),
            ('Log out', reverse('users.logout')),
        ]
        self._test_auth_nav(expected)


class TestMobilePersonas(TestMobile):
    fixtures = TestMobile.fixtures + ['addons/persona']

    def test_personas_home(self):
        r = self.client.get(reverse('browse.personas'))
        eq_(r.status_code, 200)
        self.assertTemplateUsed(
            r, 'browse/personas/mobile/category_landing.html')
        eq_(r.context['category'], None)
        assert 'is_homepage' in r.context

    def test_personas_home_title(self):
        r = self.client.get(reverse('browse.personas'))
        doc = pq(r.content)
        eq_(doc('title').text(), 'Themes :: Add-ons for Firefox')

    def test_personas_search(self):
        r = self.client.get(reverse('browse.personas'))
        eq_(r.context['search_cat'], 'themes')
        s = pq(r.content)('#search')
        eq_(s.attr('action'), reverse('search.search'))
        eq_(s.find('input[name=q]').attr('placeholder'), 'search for themes')
        eq_(s.find('input[name=cat]').val(), 'themes')

    def _create_persona_cat(self):
        category = Category(type=amo.ADDON_PERSONA, slug='xxx',
                            application=amo.FIREFOX.id)
        category.save()
        return category

    def test_personas_grid(self):
        """Ensure we always hit grid page if there's a category or sorting."""
        grid = 'browse/personas/mobile/grid.html'

        category = self._create_persona_cat()
        category_url = reverse('browse.personas', args=[category.slug])

        # Even if the category has 5 add-ons.
        category.count = 5
        category.save()
        r = self.client.get(category_url)
        self.assertTemplateUsed(r, grid)

        # Show the grid page even with sorting.
        r = self.client.get(reverse('browse.personas') + '?sort=created')
        self.assertTemplateUsed(r, grid)
        r = self.client.get(category_url + '?sort=created')
        self.assertTemplateUsed(r, grid)

    def test_personas_category_title(self):
        r = self.client.get(reverse('browse.personas',
                                    args=[self._create_persona_cat().slug]))
        doc = pq(r.content)
        eq_(doc('title').text(), 'None Themes :: Add-ons for Firefox')

    def test_personas_sorting_title(self):
        r = self.client.get(reverse('browse.personas') + '?sort=up-and-coming')
        doc = pq(r.content)
        eq_(doc('title').text(), 'Up & Coming Themes :: Add-ons for Firefox')
