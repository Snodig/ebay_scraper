#! python3

# Description:
# By default, reads 'inventory.txt' from the current working directory. This must be a lackey-formatted decklist/inventory.
# A single card, or a python-list of cards can be passed as argv[1:] to search on the fly.

# TODOs:

# Add rickstock and vtesfrance? Title formats are similar
# Partial startswith matches (Gerard vs Gerard Rafin etc)
# Lots of weird special characters
# Searching for crypt cards within lots

# Real eBay search issues:
# 'Fahd al-Zawba'a
# "Aaron Duggan, Cameron's Toady"
# 'Grendel the Worm-Eaten'

import requests
from bs4 import BeautifulSoup
import sys, pdb
import re
import urllib
import time
import traceback
import os

storenames = ["melvin-lightfoot", "vtesfrance", "rickstock"]

def format_search_term(term):
    term = term.lower()
    if term.startswith('the '):
        term = term[4:]
    if term.endswith(', the'):
        #term = 'The ' + term[:len(term)-len(', The')]
        term = term[:len(term)-5]
    if term.endswith(', an'):
        term = 'an ' + term[:len(term)-len(', an')]
    term = term.replace("’",'')
    #term = term.replace("'",'') # Messes up the search
    term = term.replace("ö",'o')
    term = term.replace("ø",'o')
    term = term.replace("ä",'a')
    term = term.replace("å",'a')
    term = term.replace("ë",'e')
    term = term.replace("æ",'e')
    term = term.replace("(tm)",'')
    term = term.replace('(adv)', 'advanced')
    term = term.replace('(G6)', 'Fifth Edition')
    term = term.replace('(G7)', 'Fifth Edition')

    if '"' in term:
        term = term[0:term.find('"')-1] + term[term.rfind('"')+1:len(term)]

    return term

def get_data(store, card):
    searchterm = format_search_term(card)
    if '-' in searchterm:
        split = searchterm.split('-')
        if len(split) == 2:
            # Remove both words connected by the hyphen
            splitpos1 = split[0].rfind(' ')
            splitpos2 = split[1].find(' ')
            split1 = ''
            split2 = ''

            if splitpos1 != -1:
                split1 = split[0][:splitpos1]
            if splitpos2 != -1:
                split2 = split[1][splitpos2:]

            if len(split1.strip()) != 0 or len(split2.strip()) != 0:
                searchterm = split1 + split2
                
    searchterm = urllib.parse.quote(searchterm)

    url = f'https://www.ebay.com/sch/i.html?_dkr=1\
&_ssn={store}\
&store_cat=0\
&_oac=1\
&_nkw={searchterm}'
# &LH_Sold=1\
# &LH_Complete=1\

    #print(url)
    r = requests.get(url)
    soup = BeautifulSoup(r.text, 'html.parser')
    return soup

def parse(soup, store, card, is_crypt=False):
    card = format_search_term(card).replace("'", '')
    productslist = list()
    results = soup.find_all('div', {'class': 's-item__wrapper clearfix'})
    #results = soup.find_all('div', {'class': 's-item__title'})
    for item in results:
        title = item.find('div', {'class': 's-item__title'}).text

        if title == 'Shop on eBay':
            continue

        title_lower = format_search_term(title).replace("'", '');

        is_lot = ' lot ' in title_lower

        if not title_lower.replace("'",'').startswith(card.lower().replace("'",'')) and not is_lot:
            #print('Result discarded: ' + title_lower)
            continue

        # TODO: The fuzzy matching in lots will yield "Lucinde, Alastor" for "Alastor"

        # TODO: Should really be a 2-pass process, singles first, then use the lot if no hits on singles.
        # This does look weird for cards like Horatio or Alastor though.

        if is_lot:
            if len(productslist) == 0:
                print('Found in lot (kept): ' + title)
            else:
                print('Found in lot (discarded): ' + title)
                continue

        rx1 = re.search('x\\d+', title)
        rx2 = re.search('\\d+x', title)

        numitems = '1'
        title_isolated = title_lower
        if rx1:
            numitems = title[rx1.start()+1:rx1.end()]
            title_isolated = title_isolated[:rx1.start()-1]
        elif rx2:
            numitems = title[rx2.start():rx2.end()-1]
            title_isolated = title_isolated[:rx2.start()-2]
        elif title_isolated.lower().startswith(card.lower()):
            title_isolated = card        

        if not title_isolated.lower().startswith(card.lower()) and not is_lot:
            print('"' + card + '" - Found fuzzy (discarded): "' + title_isolated.lower() + '"')
            continue

        soldprice = item.find('span', {'class': 's-item__price'}).text
        #print(soldprice)
        if 'EUR' in soldprice or '$' in soldprice: # Can we extract the estimated price in NOK when this happens? <- No! Will have to look up current exchange rates (at script start).
             # Root of Vitality (rickstock, $1)
             # Tropy: Retainers (melvin-lightfoot, $1)
             # Ayelea, The Manipulator (melvin-lightfoot, 0,92 EUR)
             # Victor Tolliver (rickstock, $3.00)
            pdb.set_trace()
        soldprice = soldprice.replace('NOK','').replace('$','').replace('EUR','').replace(',','').strip()
        soldprice = soldprice.split(' ')[0] # In case price is a range (X NOK to Y NOK)
        soldprice = round(float(soldprice) / int(numitems), 3) # Prices are always per single
        link = item.find('a', {'class': 's-item__link'})['href']

        product = {
            'title': title,
            'soldprice': soldprice,
            'link': link,
            'store': store
        }

        #print(card + ': ' + str(product))
        productslist.append(product)

    return productslist

def output(productslist, searchterm):
    productsdf = pd.DataFrame(productslist)
    productsdf.to_csv(searchterm + 'inventory.csv', index=False)
    print('Saved to CSV')
    return

def main():
    try:
        print("Start time\t\t", time.strftime("%H:%M:%S"))
        t0 = time.localtime()
        print("Working in", os.getcwd())

        cardinfos = dict()

        if(len(sys.argv) > 1):
            for card in sys.argv[1:]:
                cardinfos[card] = {'count': 1, 'price': 0, 'link': ''}
        else:
            f = open('inventory.txt', 'r')
            inventory = f.readlines()
            for line in inventory:
                if line.startswith('Crypt:'):
                    continue
                card = line[line.find(' '):].strip()
                count = line[:line.find(' ')]
                cardinfos[card] = {'count': int(count), 'price': 0, 'link': ''}
            f.close()


        totalvalue = 0
        unknown_prices = list()
        for card in cardinfos:
            print("\nSearching for: " + card)
            listings = list()
            for store in storenames:
                try:
                    soup = get_data(store, card)
                    listings += parse(soup, store, card)
                except KeyboardInterrupt:
                    raise
                except:
                    print("\n")
                    traceback.print_exc()
                    continue

            if len(listings) == 0:
                print('No results')
                unknown_prices.append(card)
                continue

            for sale in listings:
                #print(sale['store'] + " - " + str(sale['soldprice']) + " v " + str(cardinfos[card]['price']) + " (" + str(sale['soldprice'] < cardinfos[card]['price']) + ")")
                if cardinfos[card]['price'] == 0 or sale['soldprice'] < cardinfos[card]['price']:
                    cardinfos[card]['link'] = sale['link']
                    cardinfos[card]['store'] = sale['store']
                    cardinfos[card]['price'] = sale['soldprice']

            value = round(cardinfos[card]['price'] * cardinfos[card]['count'], 3)
            totalvalue += value
            totalvalue = round(totalvalue, 3)

            print(card + ' (' + str(cardinfos[card]['count']) + 'x*' + str(cardinfos[card]['price']) + '=' + str(value) + ')')
            print(cardinfos[card]['link'] + " (" + cardinfos[card]['store'] + ")")
            print('Total Value NOK ' + str(totalvalue))

    except KeyboardInterrupt:
        print("\n-- Ctrl^C ---")

    except:
        print("\n")
        traceback.print_exc()

    finally:
        print()
        print('Best prices:')
        for card in cardinfos:
            if cardinfos[card]['link'] != '':
                print(card + ': NOK ' + str(cardinfos[card]['price']) + ' ( ' + cardinfos[card]['link'] + ' )')

        if len(unknown_prices) > 0:
            print()
            print('Unknowns (' + str(len(unknown_prices)) + '):')
            print(unknown_prices)


        print()
        print('Total Value NOK ' + str(totalvalue))

        print()
        print("Time is now\t\t", time.strftime("%H:%M:%S"))
        totalTime = time.mktime(time.localtime()) - time.mktime(t0)
        print("Running since\t", time.strftime("%H:%M:%S", t0), "(", totalTime, "seconds )")

if __name__ == "__main__":
    main()