import requests
from bs4 import BeautifulSoup as bs
import sqlite3
import matplotlib.pyplot as plt
import calendar


# Having the search term and its category in one object makes it easier to categorize articles
class SearchTerm:

    def __init__(self, term, category):
        self.term = term
        self.category = category


# Having an article object reduces the amount of code needed to categorize articles
class Article:

    def __init__(self, url, domain_id):
        self.url = url
        self.domain_id = domain_id
        self.text = ""


# This decorator function handles the connection to the database
def connector(function):
    def wrapper(*args):
        connection = sqlite3.connect("news.db")
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys = True")
        result = function(cursor, *args)
        connection.commit()
        cursor.close()
        connection.close()
        return result

    return wrapper


# This function scrapes article urls from the front page of reuters
def scrape_reuters():
    domain_url = "https://reuters.com"

    response = requests.get(domain_url)

    soup = bs(response.content, "html.parser")

    with_picture = soup.find_all("div", attrs={"data-testid": "MediaStoryCard"})
    no_picture = soup.find_all("div", attrs={"data-testid": "TextStoryCard"})

    article_urls = set()

    for article in with_picture:
        if "https://www.reuters.com" in article.find("a", attrs={"data-testid": "Heading"})["href"]:
            article_urls.add(article.find("a", attrs={"data-testid": "Heading"})["href"])
        else:
            article_urls.add(domain_url + article.find("a", attrs={"data-testid": "Heading"})["href"])

    for article in no_picture:
        if "https://www.reuters.com" in article.find("a", attrs={"data-testid": "Heading"})["href"]:
            article_urls.add(article.find("a", attrs={"data-testid": "Heading"})["href"])
        else:
            article_urls.add(domain_url + article.find("a", attrs={"data-testid": "Heading"})["href"])

    add_urls(article_urls, domain_url)


# This function scrapes article urls from the front page of apnews
def scrape_ap():
    domain_url = "https://apnews.com"

    response = requests.get(domain_url)

    soup = bs(response.content, "html.parser")

    main_story = soup.find("div", attrs={"data-tb-region": "Top Stories"})
    feed = soup.find_all("div", attrs={"data-key": "feed-card-hub-peak"})

    article_urls = set()

    for thing in main_story.find_all("a", attrs={"data-key": "card-headline"}):
        if "?" in thing["href"]:
            article_urls.add(domain_url + thing["href"].split("?")[0])
        else:
            article_urls.add(domain_url + thing["href"])

    for thing in feed:
        for stuff in thing.find_all("li"):
            try:
                if "?" in stuff.find("a")["href"]:
                    article_urls.add(domain_url + stuff.find("a")["href"].split("?")[0])
                else:
                    article_urls.add(domain_url + stuff.find("a")["href"])
            except Exception:
                pass

    add_urls(article_urls, domain_url)


# This function removes punctuation and splits text in to a list of words so that I can search the list for search terms
def separate_words(words):
    separated = words.replace(",", "").replace(".", "").replace('“', "").replace("’", " ").replace("‘", "").replace("-", " ").replace("”", "").replace('"', "").replace("'", " ").replace(":", "").replace("/", " ").lower().split()
    return separated


# This function adds the scraped urls into the database, but it first makes sure that the url hasn't already been saved
@connector
def add_urls(cursor, article_urls, domain_url):
    old_articles = []
    checked_urls = []

    for row in cursor.execute("select url from unscraped_articles"):
        old_articles.append(row[0])

    for row in cursor.execute("select url from scraped_articles"):
        old_articles.append(row[0])

    for art in article_urls:
        if art not in old_articles:
            checked_urls.append(art)

    cursor.execute(f"select id from domains where domain = '{domain_url}'")
    domain_id = cursor.fetchone()[0]

    for url in checked_urls:
        cursor.execute("insert into unscraped_articles (domain_id, url) values (?, ?)", (domain_id, url))
        

# This function adds a search term to the database and makes sure that the search term doesn't already exist
@connector
def add_term(cursor, term, category_id):
    for row in cursor.execute("select term from search_terms"):
        if row[0] == term:
            print("That search term already exists")
            return
    cursor.execute("insert into search_terms (category_id, term) values (?, ?)", (category_id, term))


# This function adds a category to the database and makes sure that the category doesn't already exist
@connector
def add_category(cursor, category):
    for row in cursor.execute("select category from categories"):
        if row[0] == category:
            print("That category already exists")
            return
    cursor.execute("insert into categories (category) values (?)", (category,))


# This function adds a domain to the database and makes sure that the domain doesn't already exist
@connector
def add_domain(cursor, domain):
    for row in cursor.execute("select domain from domains"):
        if row[0] == domain:
            print("That domain already exists")
            return
    cursor.execute("insert into domains (domain) values (?)", (domain,))


# This function scrapes the articles and categorizes them
@connector
def scrape_articles(cursor):
    search_terms = []
    for row in cursor.execute("select category_id, term from search_terms"):
        search_terms.append(SearchTerm(row[1].lower(), row[0]))

    articles = []
    for row in cursor.execute("select url, domain_id from unscraped_articles"):
        articles.append(Article(row[0], row[1]))

    scraped_articles = []
    for article in articles:
        article_content = requests.get(article.url)
        soup = bs(article_content.content, "html.parser")
        paragraphs = soup.find_all("p")
        # This dictionary stores the categories in the keys and their appearances in the values
        category_counter = {}
        for par in paragraphs:
            article.text += par.text + " "
            words = separate_words(par.text)
            previous_word = ""
            for word in words:
                for search_term in search_terms:
                    if word == search_term.term or previous_word + " " + word == search_term.term:
                        try:
                            category_counter[search_term.category] += 1
                        except KeyError:
                            category_counter[search_term.category] = 1
                previous_word = word
        # This sorts the dictionary based on the key values and returns a list of tuples
        sorted_categories = sorted(category_counter.items(), key=lambda x: x[1], reverse=True)
        try:
            # The most commonly seen category will be the first element in the tuple in the first position of the list
            category = sorted_categories[0][0]
        except IndexError:
            category = None
        scraped_articles.append((article.domain_id, article.url, article.text, category))
    cursor.execute("delete from unscraped_articles")
    cursor.executemany("insert into scraped_articles (domain_id, url, text, category_id) values (?,?,?,?)", scraped_articles)
    

# This function counts the occurrence of a specific search term over days or months
@connector
def count_word_occurrence(cursor, search_word, month=False):
    articles = []
    # This dictionary stores dates in the keys and the occurrence of the search word on that date in the value
    word_count = {}
    if month == False:
        for row in cursor.execute("select text, date from scraped_articles"):
            articles.append((row[0], row[1]))
            # Here I assign the keys to the dictionary and set their starting value to 0
            word_count[row[1]] = 0
    else:
        for row in cursor.execute("select text, date from scraped_articles"):
            # Here I use the calendar.month_name function to get the name of the month
            articles.append((row[0], calendar.month_name[int(row[1].split("-")[1])]))
            word_count[calendar.month_name[int(row[1].split("-")[1])]] = 0

    for art in articles:
        previous_word = ""
        words = separate_words(art[0])
        for word in words:
            if word == search_word or previous_word + " " + word == search_word:
                word_count[art[1]] += 1
            previous_word = word
    return word_count


# This function fetches the amount of articles of a certain category per day from the database
@connector
def count_category_occurrence(cursor, category_id):
    # This dictionary stores the dates as keys and amount of articles as values
    categories = {}
    for row in cursor.execute(f"select count(*), date from scraped_articles group by date, category_id having category_id = '{category_id}'"):
        # Here I assign the value as the amount of articles
        categories[row[1]] = row[0]
    return categories


# This function counts the total occurrence of each category
@connector
def count_total_category_occurrence(cursor):
    search_terms = []
    for row in cursor.execute("select category_id, term from search_terms"):
        search_terms.append(SearchTerm(row[1].lower(), row[0]))

    # This dictionary stores the categories in the keys and their occurrence in the values
    total_category_count = {}
    # Here I fetch the actual category names because I need them for writing the graph
    for term in search_terms:
        cursor.execute(f"select category from categories where id = {term.category}")
        term.category = cursor.fetchone()[0]
        # Here I assign the starting value at each key to 0
        total_category_count[term.category] = 0

    articles = []
    for row in cursor.execute("select text from scraped_articles"):
        articles.append(row[0])

    for article in articles:
        category_counter = {}
        words = separate_words(article)
        previous_word = ""
        for word in words:
            for search_term in search_terms:
                if word == search_term.term or previous_word + " " + word == search_term.term:
                    try:
                        category_counter[search_term.category] += 1
                    except KeyError:
                        category_counter[search_term.category] = 1
            previous_word = word
        sorted_categories = sorted(category_counter.items(), key=lambda x: x[1], reverse=True)
        try:
            total_category_count[sorted_categories[0][0]] += 1
        # Here I set the category to "None" in case none of my search terms are in the article
        except IndexError:
            try:
                total_category_count["None"] += 1
            except KeyError:
                total_category_count["None"] = 1
    return total_category_count


# This function plots the occurrence of one search term or two search terms or a category over days or months
def plot_word_occurrence(word_count, search_word, word_count_2=None, search_word_2=None):
    plt.plot(word_count.keys(), word_count.values(), 'o-', label=search_word)
    if word_count_2 == None and search_word_2 == None:
        plt.title(f"Occurence of {search_word} in news articles")
    else:
        plt.plot(word_count_2.keys(), word_count_2.values(),'o-', label=search_word_2)
        plt.title(f"Occurence of {search_word} and {search_word_2} in news articles")
    plt.legend(loc="best")
    plt.xlabel("Date")
    plt.ylabel("Occurrence")
    print("You have to close the graph window to continue using the program")
    plt.show()


# This function makes a bar graph showing the amount of articles of each category
def bar_category_occurrence(category_count):
    plt.bar(category_count.keys(), category_count.values())
    plt.title("Occurrence of categories")
    plt.xlabel("Category")
    plt.ylabel("Occurrence")
    print("You have to close the graph window to continue using the program")
    plt.show()


# This function shows all categories, it can show indexes if I want the user to select a category and it can return a dictionary with category names if I want them
@connector
def see_categories(cursor, just_print=False, return_dict=False):
    dict_of_categories = {}
    for index, row in enumerate(cursor.execute("select category from categories"), 1):
        # Because I always get the categories in order when I fetch, I can simply use the enumerate function to create a dict with their ids
        dict_of_categories[index] = row[0]
        if just_print == False:
            print(f"[{index}]", dict_of_categories[index].title())
        else:
            print(dict_of_categories[index].title())
    if return_dict == False:
        return dict_of_categories.keys()
    else:
        return dict_of_categories
    

# This function shows all search terms of a certain category with their indexes and returns them in a dictionary
@connector
def see_search_terms(cursor, category_id):
    dict_of_terms = {}
    for index, row in enumerate(cursor.execute(f"select term from search_terms where category_id = {category_id}"), 1):
        dict_of_terms[index] = row[0]
        print(f"[{index}]", dict_of_terms[index].title())
    return dict_of_terms


# This function shows all domains
@connector
def see_domains(cursor):
    for row in cursor.execute("select domain from domains"):
        print(row[0])


# This function saves all urls from scraped articles to a .txt file
@connector
def save_urls_to_file(cursor):
    urls = []
    for row in cursor.execute("select url from scraped_articles"):
        urls.append(row[0])
    with open("news urls.txt", "w") as file:
        for url in urls:
            file.write(url + "\n")
    print(f'I\'ve saved {len(urls)} urls to a file named "news urls".')


class Menu:

    def __init__(self):
        self.start_main_menu()

    # This function is the menu
    def start_main_menu(self):
        print("Welcome to the Online Media Sentiment Tracker!")
        print("Maximize the size of your terminal for best user experience")

        while True:
            print("What would you like to do? \n"
                  "[1] See a list of the categories \n"
                  "[2] See a plot of the occurrences of a search term \n"
                  "[3] See a plot comparing the occurrences of two different search terms \n"
                  "[4] See the monthly statistics of a search term \n"
                  "[5] See a plot of the occurrences of articles of a category \n"
                  "[6] See a bar graph of total occurrences of every category \n"
                  "[7] See a list of the domains that the articles are from \n"
                  "[8] Save a list of all the URLs that have been stored to a file \n"
                  "[9] Add a search term \n"
                  "[0] Add a category  \n"
                  "[10] Add a domain \n"
                  "[s] Scrape articles from the web \n"
                  "[q] Quit")
            available_options = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "10", "q", "s"]
            user_input = input().lower()
            if user_input not in available_options:
                print("That is not an option, try again")
                continue
            if user_input == "q":
                break
            if user_input == "s":
                print("Scraping in progress...")
                scrape_ap()
                print("Scraping in progress...")
                scrape_articles()
                print("Scraping in progress...")
                scrape_reuters()
                print("Scraping in progress...")
                scrape_articles()
                print("Scraping finished")
                input("Press Enter to continue")
            if user_input == "1":
                see_categories(True)
                input("Press Enter to continue")
            if user_input == "2":
                print("What category is the search term in?")
                category_id_list = see_categories()
                try:
                    category_for_search_term_index = int(input())
                except ValueError:
                    print("That is not a number")
                    continue
                if category_for_search_term_index not in category_id_list:
                    print("That is not a valid number")
                    continue
                else:
                    print("What search term would you like to see the occurrences of?")
                    search_terms_dict = see_search_terms(
                        category_for_search_term_index)
                    try:
                        search_term_index = int(input())
                    except ValueError:
                        print("That is not a number")
                        continue
                    if search_term_index not in search_terms_dict:
                        print("That is not a valid number")
                        continue
                    else:
                        plot_word_occurrence(count_word_occurrence(search_terms_dict[search_term_index]), search_terms_dict[search_term_index].title())
                        input("Press Enter to continue")
            if user_input == "3":
                print("What category is the first search term in?")
                category_id_list = see_categories()
                try:
                    category_for_search_term_index = int(input())
                except ValueError:
                    print("That is not a number")
                    continue
                if category_for_search_term_index not in category_id_list:
                    print("That is not a valid number")
                    continue
                else:
                    print("What is the first search term you would like to see the occurrences of?")
                    search_terms_dict_1 = see_search_terms(category_for_search_term_index)
                    try:
                        search_term_index_1 = int(input())
                    except ValueError:
                        print("That is not a number")
                        continue
                    if search_term_index_1 not in search_terms_dict_1:
                        print("That is not a valid number")
                        continue
                    else:
                        print("What category is the second search term in?")
                        category_id_list = see_categories()
                        try:
                            category_for_search_term_index = int(input())
                        except ValueError:
                            print("That is not a number")
                            continue
                        if category_for_search_term_index not in category_id_list:
                            print("That is not a valid number")
                            continue
                        else:
                            print("And what is the second search term you would like to see the occurrences of?")
                            search_terms_dict_2 = see_search_terms(category_for_search_term_index)
                            try:
                                search_term_index_2 = int(input())
                            except ValueError:
                                print("That is not a number")
                                continue
                            if search_term_index_2 not in search_terms_dict_2:
                                print("That is not a valid number")
                                continue
                            else:
                                plot_word_occurrence(count_word_occurrence(search_terms_dict_1[search_term_index_1]),
                                search_terms_dict_1[search_term_index_1].title(), count_word_occurrence(search_terms_dict_2[search_term_index_2]),
                                search_terms_dict_2[search_term_index_2].title())
                                input("Press Enter to continue")
            if user_input == "4":
                print("What category is the search term in?")
                category_id_list = see_categories()
                try:
                    category_for_search_term_index = int(input())
                except ValueError:
                    print("That is not a number")
                    continue
                if category_for_search_term_index not in category_id_list:
                    print("That is not a valid number")
                    continue
                else:
                    print("For what search term would you like to see the monthly statistics?")
                    search_terms_dict_monthly = see_search_terms(category_for_search_term_index)
                    try:
                        search_term_index_monthly = int(input())
                    except ValueError:
                        print("That is not a number")
                        continue
                    if search_term_index_monthly not in search_terms_dict_monthly:
                        print("That is not a valid number")
                        continue
                    else:
                        plot_word_occurrence(count_word_occurrence(search_terms_dict_monthly[search_term_index_monthly], True),
                        search_terms_dict_monthly[search_term_index_monthly].title())
                        input("Press Enter to continue")
            if user_input == "5":
                category_dict = see_categories(False, True)
                print("What category would you like to see the occurrences of?")
                try:
                    category_id = int(input())
                except ValueError:
                    print("That is not a number")
                    continue
                if category_id not in category_dict:
                    print("That is not a valid number")
                    continue
                else:
                    plot_word_occurrence(count_category_occurrence(category_id), category_dict[category_id].title())
                    input("Press Enter to continue")
            if user_input == "6":
                print("It will take a few seconds to categorize every article")
                bar_category_occurrence(count_total_category_occurrence())
                input("Press Enter to continue")
            if user_input == "7":
                see_domains()
                input("Press Enter to continue")
            if user_input == "8":
                save_urls_to_file()
                input("Press Enter to continue")
            if user_input == "9":
                print("What category would you like that search term to be in?")
                print("These are the categories:")
                category_id_list = see_categories()
                try:
                    category_id_for_search_term = int(input())
                except ValueError:
                    print("That is not a number")
                    continue
                if category_id_for_search_term not in category_id_list:
                    print("That is not a valid number")
                    continue
                else:
                    print("What search term do you want to add? It can be a maximum of two words")
                    search_term_to_add = input().lower()
                    if search_term_to_add == "":
                        print("You can't add an empty search term")
                        continue
                    elif len(search_term_to_add.split()) > 2:
                        print("A search term can't be longer than two words")
                        continue
                    else:
                        add_term(search_term_to_add, category_id_for_search_term)
                        input("Press Enter to continue")
            if user_input == "0":
                print("What category would you like to add?")
                category_to_add = input().lower()
                if category_to_add == "":
                    print("You can't add an empty category")
                    continue
                else:
                    add_category(category_to_add)
                    input("Press Enter to continue")
            if user_input == "10":
                print("What domain would you like to add?")
                domain_to_add = input().lower()
                if "https://" not in domain_to_add:
                    print("That is not a valid domain(https:// has to be included at the start)")
                    continue
                else:
                    if domain_to_add == "":
                        print("You can't add an empty domain")
                        continue
                    else:
                        add_domain(domain_to_add)
                        input("Press Enter to continue")


@connector
def check_scraped(cursor):
    cursor.execute("select count(*) from scraped_articles")
    print(cursor.fetchall())


@connector
def check_unscraped(cursor):
    cursor.execute("select * from unscraped_articles")
    print(cursor.fetchall())


@connector
def remove_article(cursor):
    cursor.execute("delete from unscraped_articles where id = 1")


@connector
def check_all_categories(cursor):
    cursor.execute("select category from categories")
    print(cursor.fetchall())


@connector
def check_uncategorized(cursor):
    cursor.execute(
        "select count(*) from scraped_articles where category_id = None")
    print(cursor.fetchall())


@connector
def check_categories_amount(cursor):
    cursor.execute(
        "select category, count(*) from scraped_articles group by category")
    print(cursor.fetchall())


@connector
def check_categories(cursor):
    for row in cursor.execute("select domains.id, domain_id, domain, url from domains inner join scraped_articles on scraped_articles.domain_id = domains.id "):
        print(row)


@connector
def check_uncategorized(cursor):
    for row in cursor.execute("select count(*) from scraped_articles where category_id = NULL"):
        print(row)


@connector
def check_all_search_terms(cursor):
    cursor.execute("select term from search_terms")
    print(cursor.fetchall())


@connector
def change_category(cursor):
    cursor.execute(
        "update categories set category = 'entertainment' where category = 'Entertainment'")


@connector
def check_new_uncategorized(cursor):
    cursor.execute(
        "select url, category from scraped_articles where date = '2023-02-28' and category = 'None'")
    print(cursor.fetchall())


@connector
def categorize_uncategorized(cursor):
    search_terms = []
    for row in cursor.execute("select category_id, term from search_terms"):
        search_terms.append(SearchTerm(row[1].lower(), row[0]))
    articles = []
    for term in search_terms:
        cursor.execute(
            f"select category from categories where id = {term.category}")
        term.category = cursor.fetchone()[0]
    for row in cursor.execute("select text, id from scraped_articles where category = 'None'"):
        articles.append((row[0], row[1]))
    for article in articles:
        category_counter = {}
        words = separate_words(article[0])
        previous_word = ""
        for word in words:
            for search_term in search_terms:
                if word == search_term.term or previous_word + " " + word == search_term.term:
                    # print(search_term.term)
                    try:
                        category_counter[search_term.category] += 1
                    except KeyError:
                        category_counter[search_term.category] = 1
            previous_word = word
        sorted_categories = sorted(
            category_counter.items(), key=lambda x: x[1], reverse=True)
        try:
            category = sorted_categories[0][0]
        except IndexError:
            category = "None"
        # print(article[1], category)
        cursor.execute(
            f"update scraped_articles set category = '{category}' where id = {article[1]}")


@connector
def check_some_arts(cursor):
    for row in cursor.execute("select url, text, category from scraped_articles where id = 725"):
        print(row)


@connector
def change_from_category_to_id(cursor):
    # cursor.execute("update scraped_articles set scraped_articles.category_id = categories.category_id where scraped_articles.category = categories.category")
    cursor.execute("select scraped_articles.category, categories.category, categories.id from scraped_articles inner join categories on categories.category = scraped_articles.category")
    print(cursor.fetchall())


# change_from_category_to_id()
# check_some_arts()
check_uncategorized()
# check_all_categories()
# check_categories()
# check_unscraped()
check_scraped()
# check_all_search_terms()
# change_category()
# check_new_uncategorized()
# categorize_uncategorized()
if __name__ == "__main__":
    menu = Menu()
# check_unscraped()
check_scraped()
check_uncategorized()
# check_categories()
# check_all_categories()
# check_all_search_terms()
